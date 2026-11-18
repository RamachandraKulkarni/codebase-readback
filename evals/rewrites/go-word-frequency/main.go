package main

import (
	"bufio"
	"fmt"
	"io"
	"os"
	"sort"
	"strconv"
	"strings"
)

const (
	defaultTopCount  = 3
	defaultMinLength = 1
	usage            = "usage: wordfreq [top] [min-length]"
)

type wordCount struct {
	word  string
	count int
}

// CountWords counts each word of at least minLength bytes, lower-cased, with surrounding apostrophes removed.
func CountWords(text string, minLength int) map[string]int {
	countByWord := map[string]int{}
	for _, rawWord := range strings.FieldsFunc(text, isWordSeparator) {
		word := strings.ToLower(strings.Trim(rawWord, "'"))
		if minLength <= len(word) && "" != word {
			countByWord[word]++
		}
	}
	return countByWord
}

func isWordSeparator(character rune) bool {
	isLetter := 'a' <= character && character <= 'z' || 'A' <= character && character <= 'Z'
	return !(isLetter || '\'' == character)
}

func main() {
	topCount, minLength := parseArguments(os.Args[1:])
	rankedWords := rankByCount(CountWords(readAllLines(os.Stdin), minLength))
	printTopWords(rankedWords, topCount)
}

// A top count that is not a number is a usage error; zero or less keeps the default.
// A minimum length that is not a number is ignored.
func parseArguments(arguments []string) (topCount int, minLength int) {
	topCount, minLength = defaultTopCount, defaultMinLength
	if 0 < len(arguments) {
		requestedTopCount, err := strconv.Atoi(arguments[0])
		if nil != err {
			fmt.Fprintln(os.Stderr, usage)
			os.Exit(2)
		}
		if 0 < requestedTopCount {
			topCount = requestedTopCount
		}
	}
	if 1 < len(arguments) {
		if requestedMinLength, err := strconv.Atoi(arguments[1]); nil == err {
			minLength = requestedMinLength
		}
	}
	return topCount, minLength
}

// Every line gets a trailing newline, including a last line that had none.
func readAllLines(input io.Reader) string {
	var text strings.Builder
	lineScanner := bufio.NewScanner(input)
	for lineScanner.Scan() {
		text.WriteString(lineScanner.Text() + "\n")
	}
	return text.String()
}

// Most frequent first; equal counts in alphabetical order.
func rankByCount(countByWord map[string]int) []wordCount {
	var rankedWords []wordCount
	for word, count := range countByWord {
		rankedWords = append(rankedWords, wordCount{word, count})
	}
	sort.Slice(rankedWords, func(left, right int) bool {
		if rankedWords[left].count == rankedWords[right].count {
			return rankedWords[left].word < rankedWords[right].word
		}
		return rankedWords[left].count > rankedWords[right].count
	})
	return rankedWords
}

func printTopWords(rankedWords []wordCount, topCount int) {
	if 0 == len(rankedWords) {
		fmt.Println("no words")
		return
	}
	for _, ranked := range rankedWords[:min(topCount, len(rankedWords))] {
		fmt.Printf("%d %s\n", ranked.count, ranked.word)
	}
}
