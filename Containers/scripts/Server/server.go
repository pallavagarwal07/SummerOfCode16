package main

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"io/ioutil"
	"math/rand"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"regexp"
	"strings"
	"time"

	"gopkg.in/mgo.v2"
	"gopkg.in/mgo.v2/bson"

	"github.com/gorilla/mux"
	"github.com/jmcvetta/napping"
	"github.com/tj/go-dropbox"
)

// Instead of failing silently, crash
// and burn in case of any error
func check(e error) {
	fmt.Println("check:", "Check called")
	if e != nil {
		panic(e)
	}
}

// Contains the nodes for the dependency
// tree. State 2 can only be leaf nodes
// and are virtual packages to prevent cycles
type Node struct {
	Id        bson.ObjectId   `bson:"_id,omitempty"`
	Cpv       string          "Cpv"
	Dep       []bson.ObjectId "Dep"
	UseFlags  [][]string      "UseFlags"
	NumStable int             "NumStable"
	State     int             "State"
	// 0: Stable
	// 1: Unstable
	// 2: Acting Stable
	// 3: Blocked
}

// Temporary struct used during input of data
// from the file. The structure is same as Node,
// but dependencies are given in form of indices
// of other nodes instead of pointers
type Tmp struct {
	Cpv       string
	Indices   []int
	UseFlags  [][]string
	NumStable int
	State     int
}

type Pair struct {
	Cpv   string
	bugID int
}

// This database maintains a map from a packages
// cpv to it's real (State !=2) node
var session *mgo.Session

var db *mgo.Collection
var stable map[string]int
var unstable map[string]int
var priority []Pair
var quick_ref map[string]Tmp

// Helpful debugging function to pretty print all
// variables passed to it (Deep print)
// Use this as a blackbox
func printVars(vars ...interface{}) {
	w := os.Stdout
	for i, v := range vars {
		fmt.Fprintf(w, "» item %d type %T:\n", i, v)
		j, err := json.MarshalIndent(v, "", "    ")
		switch {
		case err != nil:
			fmt.Fprintf(w, "error: %v", err)
		case len(j) < 3:
			w.Write([]byte(fmt.Sprintf("%+v", v)))
		default:
			w.Write(j)
		}
		w.Write([]byte("\n\n"))
	}
}

// Get the Node* object from database map
// If the object doesn't already exist,
// initialise it with sane default parameters
func get(cpv string) *Node {
	fmt.Println("get:", "Get called")
	n, err := db.Find(bson.M{"Cpv": cpv}).Limit(1).Count()
	fmt.Println("get:", "Beware: n is", n)
	check(err)
	if present := (n == 1); !present { // if not present in database
		fmt.Println("get:", "Creating a new node")
		node := new(Node)
		node.Cpv = cpv                      // it's cpv should be same as lookup key
		node.Dep = make([]bson.ObjectId, 0) // Make empty dependency list
		node.State = 1                      // Assume it to be unstable
		db.Insert(*node)                    // Add it to the database
		fmt.Println("get:", "Inserted", cpv, "to database")
	}
	var result *Node
	db.Find(bson.M{"Cpv": cpv}).One(&result)
	fmt.Println("get:", "Retrieved result", result)
	return result
}

// Function runs a DFS traversal on the directed graph and
// detects cycles in the graph. On finding a cycle, it breaks
// the cycle by creating a fake package with same cpv, but
// with no dependencies, and acting as stabilized (State 2)
// Thus, in the end, we have a directed acyclic graph (DAG)
func traverse(vertex bson.ObjectId, ancestor map[string]bson.ObjectId, visited map[string]bool) {
	fmt.Println("traverse:", "traverse called")
	// visited map is used to check for disjoint trees only
	var result *Node
	db.Find(bson.M{"_id": vertex}).One(&result)
	visited[result.Cpv] = true

	var resArr []*Node
	db.Find(bson.M{"_id": bson.M{"$in": result.Dep}}).All(&resArr)
	// Iterate over every dependency of current node
	for _, child := range resArr {
		// If there exists an ancestor with same cpv and the
		// ancestor IS this node, then we have found a cycle
		if a, pr := ancestor[child.Cpv]; pr && child.Id == a {
			// Replace this child with a fake stabilized node
			// Thus, new node -> state 2 -> same cpv -> add
			node := new(Node)
			node.Cpv = child.Cpv
			node.Dep = make([]bson.ObjectId, 0)
			node.State = 2
			db.Insert(node)

			db.Find(bson.M{"Cpv": node.Cpv, "State": 2}).One(&node)
			db.Update(bson.M{"_id": vertex}, bson.M{"$pull": bson.M{"Dep": a}})
			db.Update(bson.M{"_id": vertex}, bson.M{"$push": bson.M{"Dep": node.Id}})
		} else {
			// else, mark current as ancestor, traverse child
			// and unmark as ancestor
			ancestor[child.Cpv] = child.Id
			traverse(child.Id, ancestor, visited)
			delete(ancestor, child.Cpv)
		}
	}
}

// Function to recalculate the tree and fix all the
// cycles. This traverses over the database and calls
// traverse() over the nodes
func evaluate() {
	fmt.Println("evaluate:", "evaluate called")
	visited := make(map[string]bool)
	ancestor := make(map[string]bson.ObjectId)

	var result []struct {
		_id bson.ObjectId `bson:"_id,omitempty"`
		Cpv string        "Cpv"
	}

	db.Find(nil).Select(bson.M{"_id": 1, "Cpv": 1}).All(&result)
	for _, node := range result {
		cpv, vertex := node.Cpv, node._id
		if visited[cpv] {
			continue
		}
		ancestor[cpv] = vertex
		traverse(vertex, ancestor, visited)
		delete(ancestor, cpv)
	}
}

// Simple function to decode base64 and return string
// instead of an array of bytes
func b64decode(str string) (string, error) {
	fmt.Println("b64decode:", "b64decode called")
	parent, err1 := base64.RawURLEncoding.DecodeString(str)
	return string(parent[:]), err1
}

// Handler function for http requests to /sched-dep
func dep(w http.ResponseWriter, req *http.Request) {
	fmt.Println("dep:", "a->b (dep) called")
	// Get parent and dependency and decode them (base64)
	parent_b64 := req.URL.Query().Get("parent")
	parent, err1 := b64decode(parent_b64)
	depend_b64 := req.URL.Query().Get("dependency")
	depend, err2 := b64decode(depend_b64)

	fmt.Println("dep:", "Parent-Dependency combo", parent, "->", depend)

	// Abort if any error has occured.
	// Get the nodes for both parent and child
	if err1 == nil && err2 == nil {
		pnode := get(parent)
		cnode := get(depend)

		var result []struct {
			_id bson.ObjectId `bson:"_id,omitempty"`
			Cpv string        "Cpv"
		}

		db.Find(bson.M{"_id": bson.M{"$in": pnode.Dep}}).Select(
			bson.M{"_id": 1, "Cpv": 1}).All(&result)
		flag := false
		// Check if dependency already exists in the tree
		for _, depnode := range result {
			if depnode.Cpv == depend {
				flag = true
				break
			}
		}
		// If not, then add it and reavaluate the tree
		if !flag {
			db.Update(bson.M{"_id": pnode.Id}, bson.M{"$push": bson.M{"Dep": cnode.Id}})
			fmt.Println("dep:", "Added", pnode.Cpv, "->", cnode.Cpv)
			evaluate()
		}
		io.WriteString(w, "1")
	} else {
		io.WriteString(w, "-1")
	}
}

// Function called to mark a particular package cpv as stable
func mstable(w http.ResponseWriter, req *http.Request) {
	fmt.Println("mstable:", "mstable called")

	// Get the appropriate package from the GET parameters
	pack_b64 := req.URL.Query().Get("package")

	// Base64 decode the package name
	pack, _ := b64decode(pack_b64)

	db.Update(bson.M{"Cpv": pack}, bson.M{"State": 0})
	fmt.Println("mstable:", "Got request to mark", pack, "as stable")

	immediate_node := Tmp{Cpv: pack, Indices: make([]int, 0), State: 0}
	quick_ref[req.URL.Query().Get("id")] = immediate_node
}

// Function called to mark a particular package as UNSTABLE (blocked)
func mblock(w http.ResponseWriter, req *http.Request) {
	fmt.Println("mblock:", "mblock called")

	// Get the appropriate package from the GET parameters
	pack_b64 := req.URL.Query().Get("package")

	// Base64 decode the package name
	pack, _ := b64decode(pack_b64)

	// Increment the unstable count (We can't rely on a single
	// PC's claim)
	unstable[pack]++
	fmt.Println("mblock:", "Got request to mark", pack, "as unstable")

	immediate_node := Tmp{Cpv: pack, Indices: make([]int, 0), State: 3}
	quick_ref[req.URL.Query().Get("id")] = immediate_node

	db.Update(bson.M{"Cpv": pack}, bson.M{"State": 3})
}

// This function returns a list of all Leaf nodes which are marked
// as "not yet stabilized" (state 1)
func get_leaf_nodes(id bson.ObjectId, visited map[string]bool, serverLeaf bool) []*Node {
	fmt.Println("get_leaf_nodes:", "get_leaf_nodes called")
	// Count of unstabilized dependencies of Node (This node would
	// be a leaf node only if unstable_dep = 0)
	unstable_dep := 0

	var vertex *Node
	fmt.Println("g_l_n: ", "before crashing, id=", id)
	db.FindId(id).One(&vertex)
	// List of leaves in **this** subtree
	leaves := make([]*Node, 0)
	deps := make([]*Node, 0)

	fmt.Println("g_l_n: the vertex found was:", vertex)

	// If this package is itself not "unstabilized", then this
	// subtree doesn't matter
	if vertex.State != 1 {
		return leaves
	}

	db.Find(bson.M{"_id": bson.M{"$in": vertex.Dep}}).Select(bson.M{"_id": 1, "Cpv": 1}).All(&deps)

	// Iterate over the dependencies of this node, and update
	// unstable_dep. Also, recursively find out the leaf nodes in
	// the subtree.
	fmt.Println("get_leaf_nodes:", "Looking at deps of", vertex.Cpv)
	for _, dep := range deps {
		fmt.Println("get_leaf_nodes:", "This dep is", dep.Cpv, "with state (not want 1)", dep.State)
		if dep.State == 1 {
			if serverLeaf && len(dep.UseFlags) == 0 {
				unstable_dep++
			} else if !serverLeaf && len(dep.UseFlags) != 0 {
				unstable_dep++
			}
			leaves = append(leaves, get_leaf_nodes(dep.Id, visited, serverLeaf)...)
		}
	}
	fmt.Println("get_leaf_nodes:", "Number of unstable dep of", vertex.Cpv, "is", unstable_dep)
	if unstable_dep == 0 {
		if serverLeaf && len(vertex.UseFlags) == 0 {
			leaves = append(leaves, vertex)
		} else if !serverLeaf && len(vertex.UseFlags) != 0 {
			leaves = append(leaves, vertex)
		}
	}
	return leaves
}

func getUseFlagsFromNode(node *Node) string {
	fmt.Println("getUseFlagsFromNode:", "getUseFlagsFromNode called")
	str := ""
	for _, k := range node.UseFlags[node.NumStable] {
		str += k + " "
	}
	return str
}

// This function handles the "need package" type of request
func rpack(w http.ResponseWriter, req *http.Request) {
	fmt.Println("rpack:", "rpack called")
	visited := make(map[string]bool)
	leaves := make([]*Node, 0)

	fmt.Println("rpack:", "Package requested")

	if len(priority) == 0 {
		var result []struct {
			Id  bson.ObjectId `bson:"_id,omitempty"`
			Cpv string        "Cpv"
		}

		db.Find(nil).Select(bson.M{"_id": 1, "Cpv": 1}).All(&result)
		fmt.Println("rpack: request package got", result)

		// Iterate over all Nodes and get a list of all
		// non-stabilized leaf nodes
		for _, node := range result {
			cpv, vertex := node.Cpv, node.Id
			if visited[cpv] {
				continue
			}
			leaves = append(leaves, get_leaf_nodes(vertex, visited, false)...)
		}

		fmt.Println("rpack:", "The leaf nodes are here -", leaves)

		// If there are no such nodes, return none, else
		// choose one at Random and return.
		if len(leaves) == 0 {
			io.WriteString(w, "None")
		} else {
			rand_num := rand.Intn(len(leaves))
			io.WriteString(w,
				leaves[rand_num].Cpv+"[;;]"+getUseFlagsFromNode(leaves[rand_num]))
		}
	} else {
		//io.WriteString(w, priority[0].Cpv+"[;;]"+
		//getUseFlagsFromNode(database[priority[0].Cpv]))
		//priority = append(priority[1:], priority[0])
	}
}

// Infinite loop that periodically computes the flag combinations
// of different packages (by triggering them)
func flagTrigger() {
	fmt.Println("flagTrigger:", "flagTrigger called")

	FLAG_SOLVER_IP := os.Getenv("ORCA_FLAG_SOLVER_SERVICE_HOST")

	for true {
		visited := make(map[string]bool)
		leaves := make([]*Node, 0)

		var result []struct {
			Id  bson.ObjectId `bson:"_id,omitempty"`
			Cpv string        "Cpv"
		}

		db.Find(nil).Select(bson.M{"_id": 1, "Cpv": 1}).All(&result)

		fmt.Println("flagTrigger:", "Retrieved for tree was the array:", result)

		for _, node := range result {
			fmt.Println("flagTrigger: ", node.Cpv, node.Id)
			cpv, vertex := node.Cpv, node.Id
			if visited[cpv] {
				continue
			}
			leaves = append(leaves, get_leaf_nodes(vertex, visited, true)...)
		}
		// If there are no such nodes, return none, else
		// choose one at Random and return.
		if len(leaves) != 0 {
			rand_num := rand.Intn(len(leaves))
			url := base64.URLEncoding.EncodeToString([]byte(leaves[rand_num].Cpv))
			url = "http://" + FLAG_SOLVER_IP + "/" + url
			resp, err := http.Get(url)
			text, err := ioutil.ReadAll(resp.Body)
			if string(text) != "Ok!" {
				fmt.Println("flagTrigger:", text)
				panic(err)
			}
			resp.Body.Close()
		}
		time.Sleep(time.Minute * 1)
	}
}

// Post a comment to bugzilla with logs to a specific package
// which is of state (stable/unstable)
func addComment(bugID int, filename string, state int) {
	fmt.Println("addComment:", "addComment called")
	// URL to the bugzilla rest api
	uri := "https://bugs.gentoo.org/rest/bug/"

	// Dropbox authentication token to upload files to stabilization folder
	auth_tk := "44fUT_rUcTMAAAAAAAACwh0I0b7H5pXKNv8UJLfxpa0k5UWx4GPyiu9c5UKRaZC5"

	// Gentoo bugzilla authentication key for rest api
	// TODO: switch to environment variables
	auth_key := "l07UhITjMlHXIUydO78RiAbftSa929bYdeOuF8t5"

	// Create a url that authenticates using auth_key
	uri = uri + fmt.Sprint(bugID) + "/comment" + "?api_key=" + auth_key
	file, _ := os.Open(filename)
	if filename[0] != '/' {
		filename = "/" + filename
	}

	// Create a new dropbox configuration with the authentication token
	d := dropbox.New(dropbox.NewConfig(auth_tk))
	// Upload files to a prticular path, using the above log file as the
	// Reader and using mode 'add' (for upload)
	_, err := d.Files.Upload(&dropbox.UploadInput{
		Path:   filename,
		Reader: file,
		Mute:   true,
		Mode:   "add",
	})

	// In case the upload failed, print error and return to calling function
	if err != nil {
		fmt.Println("addComment:", "Error occured during upload: ", err)
		return
	}

	// Create a sharing link that would be available in the comment so that
	// users can access the logs.
	out, err := d.Sharing.CreateSharedLink(&dropbox.CreateSharedLinkInput{
		Path:     filename,
		ShortURL: false,
	})

	// If the URL can't be retrieved, again print error and return to calling
	// function
	if err != nil {
		fmt.Println("addComment:", "Error while retrieving URL: ", err)
		return
	}

	// The URL by default takes to a dropbox page. Replace download parameter
	// with one to directly cause download when the link is clicked
	url := out.URL
	url = strings.Replace(url, "dl=0", "dl=1", -1)

	// We don't know what the type of the response from the POST request is going
	// to be. Thus we use a universal 'interface' type.
	var result interface{}

	// Verdict is whether the build was stable or not. 3 is for unstable while
	// 1 is for stable
	var verdict string
	if state == 3 {
		verdict = "unstable"
	} else {
		verdict = "stable"
	}

	// Make the post request (comment on bugzilla)
	// Parameters are: URL
	// 				   Map string -> string : 'comment' -> comment string
	//                 Pointer to store result (interface)
	_, err = napping.Post(uri, &map[string]string{
		"comment": `
		Hi There!
		I am an automated build bot.
		I am here because you issued a stabilization request.
		On first impressions, it seems that the build is ` + verdict +
			` for amd64.
		The relevant build logs can be found here:
		` + url + `

		If you think this build was triggered in error or want
		to suggest somthing, open an issue at 
		github.com/pallavagarwal07/SummerOfCode16`}, &result, nil)
}

// Function to add package to the tree if it doesn't exist
func addpack(w http.ResponseWriter, req *http.Request) {
	fmt.Println("addpack:", "addpack called")
	pkg := req.URL.Query().Get("package")
	fmt.Println("addpack:", pkg)
	get(pkg)
	io.WriteString(w, "1")
}

func tempUrl(w http.ResponseWriter, req *http.Request) {
	url := get_temp_url()
	io.WriteString(w, url)
}

func addCombo(w http.ResponseWriter, req *http.Request) {
	fmt.Println("addCombo:", "addCombo called")
	pkg := req.URL.Query().Get("package")
	flags := req.URL.Query().Get("flags")

	fmt.Println("Combo wants to add", pkg, "with", flags)

	combo := strings.Split(flags, " ")

	var res []*Node

	db.Find(bson.M{"Cpv": pkg, "NumStable": bson.M{"$ne": 2}}).All(&res)
	fmt.Println("The update seems to be applied to: ", res, "for combo", combo)
	db.Update(bson.M{"Cpv": pkg, "NumStable": bson.M{"$ne": 2}}, bson.M{"$push": bson.M{"UseFlags": combo}})
	db.Find(bson.M{"Cpv": pkg, "NumStable": bson.M{"$ne": 2}}).All(&res)
	fmt.Println("The update seems to have been applied to: ", res[0])

	io.WriteString(w, "1")
}

// Function to handle and route all requests.
// The channel is used so that this can run on a
// separate "goroutine" and still block the main
// function when it is done
func serverStart(c chan bool) {
	fmt.Println("serverStart:", "serverStart called")
	r := mux.NewRouter()
	r.HandleFunc("/sched-dep", dep)
	r.HandleFunc("/mark-stable", mstable)
	r.HandleFunc("/mark-blocked", mblock)
	r.HandleFunc("/request-package", rpack)
	//r.HandleFunc("/submit-log", submitlog)
	r.HandleFunc("/add-package", addpack)
	r.HandleFunc("/add-combo", addCombo)
	r.HandleFunc("/temp-upload-url", tempUrl)

	// Custom http server
	s := &http.Server{
		Addr:           ":80",
		Handler:        r,
		ReadTimeout:    10 * time.Second,
		WriteTimeout:   10 * time.Second,
		MaxHeaderBytes: 1 << 20,
	}

	err := s.ListenAndServe()
	if err != nil {
		fmt.Printf("serverStart:", "Server failed: ", err.Error())
	}
	c <- true
}

type Params struct {
	f1             string
	o1             string
	v1             string
	bug_status     string
	include_fields [6]string
}

func prioritize(bug map[string]interface{}) {
	fmt.Println("prioritize:", "prioritize called")
	// This regex matches any valid package atom as defined by the gentoo guidelines
	// Writing inside `backticks` means a RAW string. Equivalent of python's r'raw_string'
	k, _ := regexp.Compile(`\w+[\w.+-]*/\w+[\w.+-]*-[0-9]+(\.[0-9]+)*[a-z]?` +
		`((_alpha|_beta|_pre|_rc|_p)[0-9]?)*(-r[0-9]+)?`)

	// Check if the title (summary) of the stablereq request contains a valid
	// package item.
	cpv := k.FindString(bug["summary"].(string))

	if cpv == "" {
		// If it doesn't, we cannot do anything about this package
		fmt.Println("prioritize:", "Could not find a valid Package in summary", bug)
	} else {
		// If it does, then we append the package to the priority list
		// and trigger a TRAVIS build for that package
		id := int(bug["id"].(float64))
		priority = append(priority, Pair{cpv, id})
		fmt.Println("prioritize:", "Adding package", Pair{cpv, id}, "to priority list")
		trigger(cpv)
	}
	//savePriority("/shared/data")
}

// This function triggers a TRAVIS build on request
func trigger(cpv string) {
	fmt.Println("trigger:", "trigger called")
	// There is another repository called TravisTrigger
	// That repository is being monitored for commits by
	// travis. this function creates a change in one of
	// the files (/triggers) and commits the changes to
	// the repository, hence triggering the build
	f, err := os.OpenFile("../TravisTrigger/triggers", os.O_APPEND|os.O_WRONLY, 0644)
	check(err)
	f.WriteString(cpv + "\n")
	f.Close()

	// Create a string containing a path to that repository.
	// Changes to that file were done above.
	// Add and commit the file. And then push the repository
	cwd := os.Getenv("PWD")
	command := `
		cd ` + cwd + `/../TravisTrigger;
		git commit -am 'Add new package for trigger'
		git push origin master
		`

	// The current script is being run as root. We don't want that to happen
	// with the commits. Thus execute the command as user pallav, using the
	// following syntax: `su -c "command" - pallav`
	_, err = exec.Command("su", "-c", command, "-", "pallav").CombinedOutput()
	check(err)

	// Rejoice
	fmt.Println("trigger:", "Triggered a Travis Build")
}

// This function periodically polls bugzilla to find out if there are any new
// STABLEREQ requests.
func bugzillaPolling(c chan bool) {
	fmt.Println("bugzillaPolling:", "bugzillaPolling called")
	// URL to the REST api of bugzilla
	uri := "https://bugs.gentoo.org/rest/bug"

	// Since this has to poll every 1 hours, run this in an infinite loop
	for true {
		// Filteration system. We want bugs that are:
		// 									1. Created from -1h to now
		//									2. Have "STABLEREQ" in keywords
		// 									3. are open
		// 									4. Retrieve id and summary
		payload := url.Values{
			"chfield":        []string{"[Bug creation]"},
			"chfieldfrom":    []string{"-1h"},
			"chfieldto":      []string{"Now"},
			"f2":             []string{"keywords"},
			"o2":             []string{"substring"},
			"v2":             []string{"STABLEREQ"},
			"bug_status":     []string{"__open__"},
			"include_fields": []string{"id", "summary"},
		}
		var response map[string][]map[string]interface{}
		_, err := napping.Get(uri, &payload, &response, nil)
		if err != nil {
			fmt.Println("bugzillaPolling:", err)
			continue
		}
		fmt.Println("bugzillaPolling:", response)

		// Assume that the request is in fact a stabilization request
		// if it contains words like stable or stabilize or request etc.
		detect := func(s string) (ans bool) {
			ans = false
			s = strings.ToLower(s)
			ans = ans || strings.Contains(s, "stable")
			ans = ans || strings.Contains(s, "stabil")
			ans = ans || strings.Contains(s, "req")
			return ans
		}

		// for each bug, detect if it is a stabilization request, and if
		// it is, then prioritize is by adding to priority queue
		for _, k := range response["bugs"] {
			send := detect(k["summary"].(string))
			if send {
				prioritize(k)
			} else {
				fmt.Println("bugzillaPolling:", "This doesn't seem like a stable request")
			}
		}

		// restart process every 1 hour (60 min)
		time.Sleep(time.Minute * 59)
	}
	c <- true
}

func main() {
	fmt.Println("main:", "main called")

	rand.Seed(time.Now().UTC().UnixNano())
	c := make(chan bool)
	//go bugzillaPolling(c)
	quick_ref = make(map[string]Tmp)
	host := os.Getenv("ORCA_DB_SERVICE_HOST")
	session, err := mgo.Dial(host)
	fmt.Println("main:", "Connected to database.", host)
	check(err)
	db = session.DB("data").C("database")
	go serverStart(c)
	go flagTrigger()
	fmt.Println("main:", "Started server on port 80")
	<-c
}
