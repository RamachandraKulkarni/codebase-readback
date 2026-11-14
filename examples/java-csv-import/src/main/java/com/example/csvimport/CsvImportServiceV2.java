package com.example.csvimport;

import java.util.ArrayList;

/**
 * New version of the import service.
 */
public class CsvImportServiceV2 {

    public ImportResult process(String csvText) {
        return new ImportResult(0, 0, new ArrayList<>());
    }
}
