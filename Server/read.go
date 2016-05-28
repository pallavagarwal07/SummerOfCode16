package main

import (
	"encoding/json"
	"fmt"
	"os"
)

func check(e error) {
	if e != nil {
		panic(e)
	}
}

func main() {
	file, err := os.Open("Hello")
	check(err)
	defer file.Close()
	b1 := make([]byte, 5000)
	var v []interface{}
	len, err := file.Read(b1)
	err = json.Unmarshal(b1[:len], &v)
	check(err)
	for i, node := range v {
		fmt.Println(node, i)
	}
}
