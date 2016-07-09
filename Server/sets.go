package main

import "fmt"
import "reflect"

type Set struct {
	set map[int]bool
}

func (set *Set) Add(i string) bool {
	_, found := set.set[i]
	set.set[i] = true
	return !found   //False if it existed already
}

func (set *Set) Delete(i string) {
	if _, found := set.set[i]; found {
		delete(set, i)
	}
}

func (set *Set) Equal(set2 *Set) {
	return reflect.DeepEqual(set1, set2)
}

