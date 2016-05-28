package main

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"

	"github.com/gorilla/mux"
)

func check(e error) {
	if e != nil {
		panic(e)
	}
}

type Node struct {
	Cpv string
	Dep []*Node

	State int
	// 0: Stable
	// 1: Unstable
	// 2: Acting Stable
	// 3: Blocked
}

type Tmp struct {
	Cpv     string
	Indices []int
	State   int
}

var database map[string]*Node

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
func add(pack *Node, hash map[*Node]int, lookup []*Node, index int) (int, []*Node) {
	if _, present := hash[pack]; !present {
		hash[pack] = index
		lookup = append(lookup, pack)
		index++
	}
	for _, dep := range pack.Dep {
		index, lookup = add(dep, hash, lookup, index)
	}
	return index, lookup
}

func readFromFile(filename string) {
	file, err := os.Open(filename)
	lookup := make([]*Node, 0)
	check(err)
	defer file.Close()
	database = make(map[string]*Node)
	b1 := make([]byte, 50000)
	var v []Tmp
	len, err := file.Read(b1)
	err = json.Unmarshal(b1[:len], &v)
	check(err)
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
	for i, tmp := range v {
		for _, dep := range tmp.Indices {
			fmt.Println(tmp)
			lookup[i].Dep = append(lookup[i].Dep, lookup[dep])
		}
	}
	printVars(lookup)
}

func saveToFile(filename string) {
	index := 0
	hash := make(map[*Node]int)
	lookup := make([]*Node, 0)
	for _, pack := range database {
		index, lookup = add(pack, hash, lookup, index)
	}

	file, err := os.OpenFile(filename, os.O_WRONLY|os.O_CREATE, 0644)
	check(err)
	defer file.Close()
	file.Write([]byte("["))
	for i, node := range lookup {
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
}

func get(cpv string) *Node {
	if _, present := database[cpv]; !present {
		node := new(Node)
		node.Cpv = cpv
		node.Dep = make([]*Node, 0)
		node.State = 1
		database[cpv] = node
	}
	return database[cpv]
}

func traverse(vertex *Node, ancestor, visited map[string]bool) {
	visited[vertex.Cpv] = true
	for index, child := range vertex.Dep {
		if ancestor[child.Cpv] && child == database[child.Cpv] {
			// Cycle detected
			node := new(Node)
			node.Cpv = child.Cpv
			node.Dep = make([]*Node, 0)
			node.State = 2
			vertex.Dep[index] = node
		} else {
			ancestor[child.Cpv] = true
			traverse(child, ancestor, visited)
			ancestor[child.Cpv] = false
		}
	}
}

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
	saveToFile("Hello")
	printVars(database)
}

func b64decode(str string) (string, error) {
	parent, err1 := base64.URLEncoding.DecodeString(str)
	return string(parent[:]), err1
}

func dep(w http.ResponseWriter, req *http.Request) {
	parent_b64 := req.URL.Query().Get("parent")
	parent, err1 := b64decode(parent_b64)
	depend_b64 := req.URL.Query().Get("dependency")
	depend, err2 := b64decode(depend_b64)

	if err1 == nil && err2 == nil {
		pnode := get(parent)
		cnode := get(depend)

		flag := false
		for _, depnode := range pnode.Dep {
			if depnode.Cpv == depend {
				flag = true
				break
			}
		}
		if !flag {
			pnode.Dep = append(pnode.Dep, cnode)
			evaluate()
		}
		io.WriteString(w, "hello, Dir!\n")
	}
	io.WriteString(w, "Invalid Arguments\n")
}

func serverStart(c chan bool) {
	r := mux.NewRouter()
	r.HandleFunc("/sched-dep", dep)

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

func main() {
	c := make(chan bool)
	go serverStart(c)
	readFromFile("Hello")
	fmt.Println("Started server on port 80")
	database = make(map[string]*Node)
	<-c
}
