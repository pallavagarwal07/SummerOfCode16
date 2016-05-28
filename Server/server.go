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

var database map[string]*Node

func printVars(w io.Writer, vars ...interface{}) {
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

type Node struct {
	Cpv string
	Dep []*Node

	State int
	// 0: Stable
	// 1: Unstable
	// 2: Acting Stable
	// 3: Blocked
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
	printVars(os.Stdout, database)
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
	fmt.Println("Started server on port 80")
	database = make(map[string]*Node)
	<-c
}
