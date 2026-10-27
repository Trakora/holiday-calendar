// Command holiday-calendar keeps a local folder in sync with the Trakora holiday calendar.
//
// It downloads the change files of every release that is not in the folder yet, checks
// their SHA-256 and records the last release in state.json. A loader then applies the files
// in order, upserting or deleting rows by the primary keys listed in manifest.json.
//
//	go run . -dir holiday-calendar
package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path"
	"time"
)

const defaultBaseURL = "https://data.trakora.com/holiday-calendar/v1"

var client = &http.Client{Timeout: 2 * time.Minute}

type file struct {
	Path   string `json:"path"`
	SHA256 string `json:"sha256"`
}

type change struct {
	Table   string `json:"table"`
	Parquet file   `json:"parquet"`
	CSV     file   `json:"csv"`
}

type release struct {
	Version    string   `json:"version"`
	ReleaseSeq int      `json:"release_seq"`
	Changes    []change `json:"changes"`
}

type manifest struct {
	Releases []release `json:"releases"`
}

type state struct {
	ReleaseSeq int    `json:"release_seq"`
	Version    string `json:"version"`
}

// Sync downloads the change files of all new releases into dir and returns their versions.
// format is "csv" or "parquet".
func Sync(baseURL, dir, format string) ([]string, error) {
	if format != "csv" && format != "parquet" {
		return nil, fmt.Errorf("format must be csv or parquet, not %q", format)
	}
	raw, err := get(baseURL + "/manifest.json")
	if err != nil {
		return nil, err
	}
	var m manifest
	if err := json.Unmarshal(raw, &m); err != nil {
		return nil, fmt.Errorf("manifest: %w", err)
	}

	if err := os.MkdirAll(dir, 0o755); err != nil {
		return nil, err
	}
	// Every write goes through root, so a path in the manifest cannot leave dir.
	root, err := os.OpenRoot(dir)
	if err != nil {
		return nil, err
	}
	defer root.Close()

	var current state
	switch saved, err := root.ReadFile("state.json"); {
	case err == nil:
		if err := json.Unmarshal(saved, &current); err != nil {
			return nil, fmt.Errorf("state.json: %w", err)
		}
	case !errors.Is(err, os.ErrNotExist):
		return nil, err
	}

	var applied []string
	for _, r := range m.Releases {
		if r.ReleaseSeq <= current.ReleaseSeq {
			continue
		}
		for _, c := range r.Changes {
			f := c.CSV
			if format == "parquet" {
				f = c.Parquet
			}
			if err := download(root, baseURL, f); err != nil {
				return applied, err
			}
		}
		// Written only once every file of the release is there, so an interrupted run repeats it.
		current = state{ReleaseSeq: r.ReleaseSeq, Version: r.Version}
		saved, _ := json.MarshalIndent(current, "", "  ")
		if err := root.WriteFile("state.json", saved, 0o644); err != nil {
			return applied, err
		}
		applied = append(applied, r.Version)
	}
	return applied, root.WriteFile("manifest.json", raw, 0o644)
}

func download(root *os.Root, baseURL string, f file) error {
	data, err := get(baseURL + "/" + f.Path)
	if err != nil {
		return err
	}
	sum := sha256.Sum256(data)
	if hex.EncodeToString(sum[:]) != f.SHA256 {
		return fmt.Errorf("checksum mismatch for %s", f.Path)
	}
	if err := root.MkdirAll(path.Dir(f.Path), 0o755); err != nil {
		return err
	}
	return root.WriteFile(f.Path, data, 0o644)
}

func get(url string) ([]byte, error) {
	resp, err := client.Get(url)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("%s: %s", url, resp.Status)
	}
	return io.ReadAll(resp.Body)
}

func main() {
	baseURL := flag.String("url", defaultBaseURL, "base URL of the holiday calendar")
	dir := flag.String("dir", "holiday-calendar", "target folder")
	format := flag.String("format", "csv", "file format of the change files: csv or parquet")
	flag.Parse()

	applied, err := Sync(*baseURL, *dir, *format)
	if err != nil {
		log.Fatal(err)
	}
	if len(applied) == 0 {
		fmt.Println("Already up to date")
		return
	}
	fmt.Printf("Downloaded %d release(s): %v\n", len(applied), applied)
}
