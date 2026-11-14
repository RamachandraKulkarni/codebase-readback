package com.example.csvimport;

import java.util.List;

public record ImportResult(int imported, int skipped, List<String> errors) {
}
