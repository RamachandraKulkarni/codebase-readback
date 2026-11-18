package main

import (
	"bufio"
	"fmt"
	"os"
	"sort"
	"strconv"
	"strings"
)

// CountWords counts the words
func CountWords(text string, minLength int) map[string]int {
	m := map[string]int{}
	for _, w := range strings.FieldsFunc(text, func(r rune) bool { return !(r >= 'a' && r <= 'z' || r >= 'A' && r <= 'Z' || r == '\'') }) {
		w = strings.ToLower(strings.Trim(w, "'"))
		if len(w) >= minLength {
			if w != "" {
				m[w] = m[w] + 1
			}
		}
	}
	return m
}

func main() {
	n := 3
	min := 1
	if len(os.Args) > 1 {
		x, err := strconv.Atoi(os.Args[1])
		if err == nil {
			if x > 0 {
				n = x
			}
		} else {
			fmt.Fprintln(os.Stderr, "usage: wordfreq [top] [min-length]")
			os.Exit(2)
		}
	}
	if len(os.Args) > 2 {
		x, err := strconv.Atoi(os.Args[2])
		if err == nil {
			min = x
		}
	}
	s := bufio.NewScanner(os.Stdin)
	t := ""
	for s.Scan() {
		t = t + s.Text() + "\n"
	}
	m := CountWords(t, min)
	type kv struct {
		k string
		v int
	}
	var l []kv
	for k, v := range m {
		l = append(l, kv{k, v})
	}
	sort.Slice(l, func(i, j int) bool {
		if l[i].v == l[j].v {
			return l[i].k < l[j].k
		}
		return l[i].v > l[j].v
	})
	for i := 0; i < len(l) && i < n; i++ {
		fmt.Printf("%d %s\n", l[i].v, l[i].k)
	}
	if len(l) == 0 {
		fmt.Println("no words")
	}
}
