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

	"github.com/gorilla/mux"
	"github.com/jmcvetta/napping"
	"github.com/tj/go-dropbox"
)

// Instead of failing silently, crash
// and burn in case of any error
func check(e error) {
	if e != nil {
		panic(e)
	}
}

// Contains the nodes for the dependency
// tree. State 2 can only be leaf nodes
// and are virtual packages to prevent cycles
type Node struct {
	Cpv string
	Dep []*Node

	UseFlags  []Set
	NumStable int
	State     int
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
	UseFlags  []Set
	NumStable int
	State     int
}

type Pair struct {
	Cpv   string
	bugID int
}

// This database maintains a map from a packages
// cpv to it's real (State !=2) node
var database map[string]*Node
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

// Add nodes and their dependencies (recursively) to
// the lookup table (needed for file input and output)
// Parameters:
//			pack *Node         : node to be added
//			hash map[*Node]int : map from node to index
//          lookup []*Node     : map from index to node
//          index              : Current index to be added to
func add(pack *Node, hash map[*Node]int, lookup []*Node, index int) (int, []*Node) {
	// IF node is NOT present in hash
	if _, present := hash[pack]; !present {
		// Add it to both hashmap and reverse lookup
		hash[pack] = index
		lookup = append(lookup, pack)
		index++
	}
	// Repeat for each of its dependencies
	for _, dep := range pack.Dep {
		index, lookup = add(dep, hash, lookup, index)
	}
	// Return the changed index and lookup list.
	// hash would've been changed in place and
	// doesn't need to be returned
	return index, lookup
}

// Read the package tree from a file
func readFromFile(folder string) {
	filename := folder + "/database"
	stable_fnm := folder + "/stable"
	unstable_fnm := folder + "/unstable"
	priority_fnm := folder + "/priority"

	// Character buffer to store input (TODO: Use a better method
	// in case the data doesn't fit in hardcoded size)
	b1 := make([]byte, 5000000)

	file, err := os.Open(filename) // Open file for reading
	check(err)                     // Check for possible errors
	defer file.Close()             // Close file when function returns

	file1, err := os.Open(stable_fnm)        // Open file for reading
	check(err)                               // Check for possible errors
	defer file1.Close()                      // Close file when function returns
	len1, err := file1.Read(b1)              // Read from the file
	check(err)                               // Again, check for errors :/
	stable = make(map[string]int)            // Reset stable map
	err = json.Unmarshal(b1[:len1], &stable) // Unmarshal string to stable map

	file2, err := os.Open(unstable_fnm)        // Open file for reading
	check(err)                                 // Check for possible errors
	defer file2.Close()                        // Close file when function returns
	len2, err := file2.Read(b1)                // Read from the file
	check(err)                                 // Again, check for errors :/
	unstable = make(map[string]int)            // Reset stable map
	err = json.Unmarshal(b1[:len2], &unstable) // Unmarshal string to stable map

	file3, err := os.Open(priority_fnm)        // Open file for reading
	check(err)                                 // Check for possible errors
	defer file3.Close()                        // Close file when function returns
	len3, err := file3.Read(b1)                // Read from the file
	check(err)                                 // Again, check for errors :/
	unstable = make(map[string]int)            // Reset stable map
	err = json.Unmarshal(b1[:len3], &priority) // Unmarshal string to stable map

	// Create a lookup from index to node address
	lookup := make([]*Node, 0)

	// Reinitialise database to clean old data (if present)
	database = make(map[string]*Node)

	// Temporary structs (containing references in form of indices)
	var v []Tmp
	// len contains number of bytes read. This is needed to slice
	// the input b1 before it is sent to json library. Also, panic
	// in case of error
	len, err := file.Read(b1)
	check(err)
	// Decode the json into a list of Tmp structs. Save it into v
	// Capture error and panic if any
	err = json.Unmarshal(b1[:len], &v)
	check(err)

	// For every element in v, we create a corresponding node
	// If the State isn't 2, we add the node to the main cpv
	// lookup database. We create an empty dependency list, which
	// would be filled up on pass two (After converting indices
	// to appropriate nodes using lookup, which is filled up on
	// this pass)
	for _, tmp := range v {
		node := new(Node)
		node.Cpv = tmp.Cpv
		node.Dep = make([]*Node, 0)
		node.State = tmp.State
		if node.State != 2 {
			database[node.Cpv] = node
		}
		lookup = append(lookup, node)
	}
	// Pass two := For every dependency, lookup up the node from
	// its index and add to the appropriate list
	for i, tmp := range v {
		for _, dep := range tmp.Indices {
			lookup[i].Dep = append(lookup[i].Dep, lookup[dep])
		}
	}
}

// Save all data structures to files in JSON format from where they
// can be read and extracted next time
func saveAll(folder string) {
	// Database that contains the main package tree
	saveDatabase(folder)

	// List of packages that have been reported as stable
	// by atleas one client
	saveStable(folder)

	// List of packages that have been reported as unstable
	// by atleast one client
	saveUnstable(folder)

	// Priority List (packages that have recently got a STABLEREQ)
	savePriority(folder)
}

// Function to store the stable list to a file
func saveStable(folder string) {
	// filename of the stable list
	stable_fnm := folder + "/stable"

	// Write Only, Create if doesn't exist, delete if it already has text
	file1, err := os.OpenFile(stable_fnm, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0644)
	check(err)
	defer file1.Close()

	// Serialize the list of structs to a JSON string
	json1, err1 := json.Marshal(stable)
	// Panic if any error happens
	check(err1)

	// Write to file and save changes
	file1.Write(json1)
	file1.Sync()

}

// Function to store the unstable list to a file
func saveUnstable(folder string) {
	unstable_fnm := folder + "/unstable"

	// Write Only, Create if doesn't exist, delete if it already has text
	file1, err := os.OpenFile(unstable_fnm, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0644)
	check(err)
	defer file1.Close()

	// Serialize the list of structs to a JSON string
	json1, err1 := json.Marshal(unstable)
	// Panic if any error happens
	check(err1)

	// Write to file and save changes
	file1.Write(json1)
	file1.Sync()

}

// Function to store the priority list to a file
func savePriority(folder string) {
	priority_fnm := folder + "/priority"

	// Write Only, Create if doesn't exist, delete if it already has text
	file1, err := os.OpenFile(priority_fnm, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0644)
	check(err)
	defer file1.Close()

	// Serialize the list of structs to a JSON string
	json1, err1 := json.Marshal(priority)
	// Panic if any error happens
	check(err1)

	// Write to file and save changes
	file1.Write(json1)
	file1.Sync()

}

func saveDatabase(folder string) {
	filename := folder + "/database"

	// Current index for which lookup is being added
	// hash: mapping from node address to their index (int)
	// lookup: mapping from index to node address
	index := 0
	hash := make(map[*Node]int)
	lookup := make([]*Node, 0)

	// For everything in the database map, add them to hash
	// and lookup (existing check is done inside add function)
	for _, pack := range database {
		index, lookup = add(pack, hash, lookup, index)
	}

	// Open file for writing.
	// O_WRONLY : only for writing
	// O_CREATE : create file if it doesn't exist
	// O_TRUNC  : Remove whatever is in the file
	file, err := os.OpenFile(filename, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0644)
	check(err)
	defer file.Close()

	// Write contents in sort of json like format, which can be read later
	// automatically by json library. Ideally, GoLang templates should be
	// used. But the use of templates seemed complicated for one time use.
	file.Write([]byte("["))
	for i, node := range lookup {
		// All references in the Dep list of nodes are converted to indices
		// using the hash (map[Node*]int). The index is same as the indices
		// in the list they are being printed
		// Fields are "Cpv", "Indices", "State" (Same as Tmp struct)
		file.Write([]byte(fmt.Sprint("{ \"Cpv\":\"", node.Cpv, "\",")))
		file.Write([]byte("\"Indices\":[ "))
		for j, dep := range node.Dep {
			if j != len(node.Dep)-1 {
				file.Write([]byte(fmt.Sprint(hash[dep], ", ")))
			} else {
				file.Write([]byte(fmt.Sprint(hash[dep])))
			}
		}
		file.Write([]byte(fmt.Sprint("], ")))
		file.Write([]byte(fmt.Sprint("\"State\":", node.State, "}")))
		if i != len(lookup)-1 {
			file.Write([]byte(","))
		}
		file.Write([]byte("\n"))
	}
	file.Write([]byte("]"))
	file.Sync()
	// Sync changes to the file. File will be autoclosed
	// later due to defer file.Close()
}

// Get the Node* object from database map
// If the object doesn't already exist,
// initialise it with sane default parameters
func get(cpv string) *Node {
	if _, present := database[cpv]; !present { // if not present in database
		node := new(Node)           // make a new node (type Node*)
		node.Cpv = cpv              // it's cpv should be same as lookup key
		node.Dep = make([]*Node, 0) // Make empty dependency list
		node.State = 1              // Assume it to be unstable
		database[cpv] = node        // Add it to the database
	}
	saveAll("/shared/data")
	return database[cpv]
}

// Function runs a DFS traversal on the directed graph and
// detects cycles in the graph. On finding a cycle, it breaks
// the cycle by creating a fake package with same cpv, but
// with no dependencies, and acting as stabilized (State 2)
// Thus, in the end, we have a directed acyclic graph (DAG)
func traverse(vertex *Node, ancestor, visited map[string]bool) {
	// visited map is used to check for disjoint trees only
	visited[vertex.Cpv] = true
	// Iterate over every dependency of current node
	for index, child := range vertex.Dep {
		// If there exists an ancestor with same cpv and the
		// ancestor IS this node, then we have found a cycle
		if ancestor[child.Cpv] && child == database[child.Cpv] {
			// Replace this child with a fake stabilized node
			// Thus, new node -> state 2 -> same cpv -> add
			node := new(Node)
			node.Cpv = child.Cpv
			node.Dep = make([]*Node, 0)
			node.State = 2
			vertex.Dep[index] = node
		} else {
			// else, mark current as ancestor, travers child
			// and unmark as ancestor
			ancestor[child.Cpv] = true
			traverse(child, ancestor, visited)
			ancestor[child.Cpv] = false
		}
	}
}

// Function to recalculate the tree and fix all the
// cycles. This traverses over the database and calls
// traverse() over the nodes
func evaluate() {
	visited := make(map[string]bool)
	ancestor := make(map[string]bool)
	for cpv, vertex := range database {
		if visited[cpv] {
			continue
		}
		ancestor[cpv] = true
		traverse(vertex, ancestor, visited)
		ancestor[cpv] = false
	}
	saveAll("/shared/data")
	printVars(database)
}

// Simple function to decode base64 and return string
// instead of an array of bytes
func b64decode(str string) (string, error) {
	parent, err1 := base64.RawURLEncoding.DecodeString(str)
	return string(parent[:]), err1
}

// Handler function for http requests to /sched-dep
func dep(w http.ResponseWriter, req *http.Request) {
	// Get parent and dependency and decode them (base64)
	parent_b64 := req.URL.Query().Get("parent")
	parent, err1 := b64decode(parent_b64)
	depend_b64 := req.URL.Query().Get("dependency")
	depend, err2 := b64decode(depend_b64)

	// Abort if any error has occured.
	// Get the nodes for both parent and child
	if err1 == nil && err2 == nil {
		pnode := get(parent)
		cnode := get(depend)

		flag := false
		// Check if dependency already exists in the tree
		for _, depnode := range pnode.Dep {
			if depnode.Cpv == depend {
				flag = true
				break
			}
		}
		// If not, then add it and reavaluate the tree
		if !flag {
			pnode.Dep = append(pnode.Dep, cnode)
			evaluate()
		}
		for _, d := range pnode.Dep {
			if d.Cpv == depend {
				io.WriteString(w, fmt.Sprint(d.State))
				return
			}
		}
		// Write a message to the request
		io.WriteString(w, "-1")
		fmt.Println("This should have never been encountered")
	} else {
		io.WriteString(w, "-1")
	}
}

// Function called to mark a particular package cpv as stable
func mstable(w http.ResponseWriter, req *http.Request) {

	// Get the appropriate package from the GET parameters
	pack_b64 := req.URL.Query().Get("package")

	// Base64 decode the package name
	pack, _ := b64decode(pack_b64)
	// Increment the stable count (We can't rely on a single PC's
	// claim)
	stable[pack]++

	immediate_node := Tmp{Cpv: pack, Indices: make([]int, 0), State: 0}
	quick_ref[req.URL.Query().Get("id")] = immediate_node

	fmt.Println("Got request to mark", pack, "as stable")
	// If two or more PC's claim that it is stable, then mark it
	// as stable
	if stable[pack] >= 2 {
		get(pack).State = 0
	}
	saveAll("/shared/data")
}

// Function called to mark a particular package as UNSTABLE (blocked)
func mblock(w http.ResponseWriter, req *http.Request) {

	// Get the appropriate package from the GET parameters
	pack_b64 := req.URL.Query().Get("package")

	// Base64 decode the package name
	pack, _ := b64decode(pack_b64)

	// Increment the unstable count (We can't rely on a single
	// PC's claim)
	unstable[pack]++
	fmt.Println("Got request to mark", pack, "as unstable")

	immediate_node := Tmp{Cpv: pack, Indices: make([]int, 0), State: 3}
	quick_ref[req.URL.Query().Get("id")] = immediate_node

	// If over 5 PC's claim a package to be unstable, mark it as
	// such
	if unstable[pack] >= 5 {
		get(pack).State = 3
	}
	saveAll("/shared/data")
}

// This function returns a list of all Leaf nodes which are marked
// as "not yet stabilized" (state 1)
func get_leaf_nodes(vertex *Node, visited map[string]bool, serverLeaf bool) []*Node {
	// Count of unstabilized dependencies of Node (This node would
	// be a leaf node only if unstable_dep = 0)
	unstable_dep := 0

	// List of leaves in **this** subtree
	leaves := make([]*Node, 0)

	// If this package is itself not "unstabilized", then this
	// subtree doesn't matter
	if vertex.State != 1 {
		return leaves
	}

	// Iterate over the dependencies of this node, and update
	// unstable_dep. Also, recursively find out the leaf nodes in
	// the subtree.
	for _, dep := range vertex.Dep {
		if dep.State == 1 {
			unstable_dep++
			leaves = append(leaves, get_leaf_nodes(dep, visited, serverLeaf)...)
		}
	}
	if unstable_dep == 0 {
		if serverLeaf && len(vertex.UseFlags) == 0 {
			leaves = append(leaves, vertex)
		} else if !serverLeaf && len(vertex.UseFlags) != 0 {
			leaves = append(leaves, vertex)
		}
	}
	return leaves
}

// This function handles the "need package" type of request
func rpack(w http.ResponseWriter, req *http.Request) {
	visited := make(map[string]bool)
	leaves := make([]*Node, 0)

	if len(priority) == 0 {
		// Iterate over all Nodes and get a list of all
		// non-stabilized leaf nodes
		for cpv, vertex := range database {
			if visited[cpv] {
				continue
			}
			leaves = append(leaves, get_leaf_nodes(vertex, visited, false)...)
		}

		// If there are no such nodes, return none, else
		// choose one at Random and return.
		if len(leaves) == 0 {
			io.WriteString(w, "None")
		} else {
			rand_num := rand.Intn(len(leaves))
			io.WriteString(w, leaves[rand_num].Cpv)
		}
	} else {
		io.WriteString(w, priority[0].Cpv)
		priority = append(priority[1:], priority[0])
	}
}

// Infinite loop that periodically computes the flag combinations
// of different packages (by triggering them)
func flagTrigger() {
	for true {
		visited := make(map[string]bool)
		leaves := make([]*Node, 0)

		for cpv, vertex := range database {
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
			url = "http://localhost:7071/" + url
			resp, err := http.Get(url)
			text, err := ioutil.ReadAll(resp.Body)
			if string(text) != "Ok!" {
				fmt.Println(text)
				panic(err)
			}
			resp.Body.Close()
		}
		time.Sleep(time.Minute * 3)
	}
}

// This function recieves the build logs from the client.
// Recieve -> Decode -> File Open -> File Write -> File Close
func submitlog(w http.ResponseWriter, req *http.Request) {
	req.ParseForm()
	req.ParseMultipartForm(200000000)
	log_b64 := req.Form.Get("log")
	id := req.Form.Get("id")
	log, _ := b64decode(log_b64)
	filename := "/shared/logs/" + req.Form.Get("filename")
	fmt.Println("filename is:" + filename)

	// Open file for writing.
	// O_WRONLY : only for writing
	// O_CREATE : create file if it doesn't exist
	// O_TRUNC  : Remove whatever is in the file
	file, err := os.OpenFile(filename, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0644)
	check(err)
	defer file.Close()

	file.Write([]byte(log))

	if node, present := quick_ref[id]; present {
		state := node.State
		cpv := node.Cpv
		for i, p := range priority {
			if p.Cpv == cpv {
				addComment(p.bugID, filename, state)
				priority = append(priority[:i], priority[i+1:]...)
				break
			}
		}
	}
}

// Post a comment to bugzilla with logs to a specific package
// which is of state (stable/unstable)
func addComment(bugID int, filename string, state int) {
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
		fmt.Println("Error occured during upload: ", err)
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
		fmt.Println("Error while retrieving URL: ", err)
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
	resp, err := napping.Post(uri, &map[string]string{
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

	printVars(resp.RawText(), err, result)

}

// Function to add package to the tree if it doesn't exist
func addpack(w http.ResponseWriter, req *http.Request) {
	pkg := req.URL.Query().Get("package")
	fmt.Println(pkg)
	get(pkg)
	io.WriteString(w, "1")
}

func addCombo(w http.ResponseWriter, req *http.Request) {
	pkg := req.URL.Query().Get("package")
	flags := req.URL.Query().Get("flags")

	combo := new(Set)
	for _, flag := range strings.Split(flags, " ") {
		combo.Add(flag)
	}

	database[pkg].UseFlags = append(database[pkg].UseFlags, *combo)
	io.WriteString(w, "1")
}

// Function to handle and route all requests.
// The channel is used so that this can run on a
// separate "goroutine" and still block the main
// function when it is done
func serverStart(c chan bool) {
	r := mux.NewRouter()
	r.HandleFunc("/sched-dep", dep)
	r.HandleFunc("/mark-stable", mstable)
	r.HandleFunc("/mark-blocked", mblock)
	r.HandleFunc("/request-package", rpack)
	r.HandleFunc("/submit-log", submitlog)
	r.HandleFunc("/add-package", addpack)
	r.HandleFunc("/add-combo", addCombo)

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
		fmt.Printf("Server failed: ", err.Error())
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
	// This regex matches any valid package atom as defined by the gentoo guidelines
	// Writing inside `backticks` means a RAW string. Equivalent of python's r'raw_string'
	k, _ := regexp.Compile(`\w+[\w.+-]*/\w+[\w.+-]*-[0-9]+(\.[0-9]+)*[a-z]?` +
		`((_alpha|_beta|_pre|_rc|_p)[0-9]?)*(-r[0-9]+)?`)

	// Check if the title (summary) of the stablereq request contains a valid
	// package item.
	cpv := k.FindString(bug["summary"].(string))

	if cpv == "" {
		// If it doesn't, we cannot do anything about this package
		fmt.Println("Could not find a valid Package in summary", bug)
	} else {
		// If it does, then we append the package to the priority list
		// and trigger a TRAVIS build for that package
		id := int(bug["id"].(float64))
		priority = append(priority, Pair{cpv, id})
		fmt.Println("Adding package", Pair{cpv, id}, "to priority list")
		trigger(cpv)
	}
	savePriority("/shared/data")
}

// This function triggers a TRAVIS build on request
func trigger(cpv string) {
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
	fmt.Println("Triggered a Travis Build")
}

// This function periodically polls bugzilla to find out if there are any new
// STABLEREQ requests.
func bugzillaPolling(c chan bool) {
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
			fmt.Println(err)
			continue
		}
		fmt.Println(response)

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
				fmt.Println("This doesn't seem like a stable request")
				printVars(k)
			}
		}

		// restart process every 1 hours (60 min)
		time.Sleep(time.Minute * 59)
	}
	c <- true
}

func main() {
	rand.Seed(time.Now().UTC().UnixNano())
	c := make(chan bool)
	go serverStart(c)
	go flagTrigger()
	//go bugzillaPolling(c)
	quick_ref = make(map[string]Tmp)
	database = make(map[string]*Node)
	// readFromFile("/shared/data")
	// saveAll("/shared/data")
	fmt.Println("Started server on port 80")
	<-c
}
