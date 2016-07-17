package main

import "reflect"

type Set struct {
	MapSet map[string]bool
}

func (MapSet *Set) Add(i string) bool {
	_, found := MapSet.MapSet[i]
	MapSet.MapSet[i] = true
	return !found //False if it existed already
}

func (MapSet *Set) Delete(i string) {
	if _, found := MapSet.MapSet[i]; found {
		delete(MapSet.MapSet, i)
	}
}

func (MapSet *Set) Equal(set2 *Set) bool {
	return reflect.DeepEqual(MapSet, set2)
}

func newSet() *Set {
	s := new(Set)
	s.MapSet = make(map[string]bool)
	return s
}
