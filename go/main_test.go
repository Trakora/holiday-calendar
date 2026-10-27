package main

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"
)

func TestSyncDownloadsNewReleasesOnce(t *testing.T) {
	server := httptest.NewServer(http.FileServer(http.Dir("../tests/fixture")))
	defer server.Close()
	baseURL := server.URL + "/holiday-calendar/v1"
	dir := t.TempDir()

	applied, err := Sync(baseURL, dir, "csv")
	if err != nil {
		t.Fatal(err)
	}
	if want := []string{"2026.01.15", "2026.02.01"}; !slices.Equal(applied, want) {
		t.Fatalf("applied %v, want %v", applied, want)
	}
	if _, err := os.Stat(filepath.Join(dir, "changes", "fact_calendar_day", "2026.02.01.csv")); err != nil {
		t.Fatal(err)
	}

	applied, err = Sync(baseURL, dir, "csv")
	if err != nil {
		t.Fatal(err)
	}
	if len(applied) != 0 {
		t.Fatalf("second run applied %v, want nothing", applied)
	}
}

func TestSyncRejectsWrongChecksum(t *testing.T) {
	broken := t.TempDir()
	if err := os.CopyFS(broken, os.DirFS("../tests/fixture")); err != nil {
		t.Fatal(err)
	}
	target := filepath.Join(broken, "holiday-calendar", "v1", "changes", "dim_date", "2026.01.15.csv")
	if err := os.WriteFile(target, []byte("date\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(http.FileServer(http.Dir(broken)))
	defer server.Close()

	if _, err := Sync(server.URL+"/holiday-calendar/v1", t.TempDir(), "csv"); err == nil {
		t.Fatal("expected a checksum error")
	}
}

func TestSyncStaysInsideTheTargetFolder(t *testing.T) {
	fixture := t.TempDir()
	if err := os.CopyFS(fixture, os.DirFS("../tests/fixture")); err != nil {
		t.Fatal(err)
	}
	manifest := filepath.Join(fixture, "holiday-calendar", "v1", "manifest.json")
	raw, err := os.ReadFile(manifest)
	if err != nil {
		t.Fatal(err)
	}
	evil := strings.Replace(string(raw), `"changes/dim_date/2026.01.15.csv"`, `"../escaped.csv"`, 1)
	if err := os.WriteFile(manifest, []byte(evil), 0o644); err != nil {
		t.Fatal(err)
	}
	// Same content as the original file, so only the path check can stop it.
	original, err := os.ReadFile(filepath.Join(fixture, "holiday-calendar", "v1", "changes", "dim_date", "2026.01.15.csv"))
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(fixture, "holiday-calendar", "escaped.csv"), original, 0o644); err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(http.FileServer(http.Dir(fixture)))
	defer server.Close()

	parent := t.TempDir()
	if _, err := Sync(server.URL+"/holiday-calendar/v1", filepath.Join(parent, "sync"), "csv"); err == nil {
		t.Fatal("expected an error for a path outside the folder")
	}
	if _, err := os.Stat(filepath.Join(parent, "escaped.csv")); err == nil {
		t.Fatal("file was written outside the target folder")
	}
}
