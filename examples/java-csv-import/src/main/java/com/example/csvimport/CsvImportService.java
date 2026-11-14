package com.example.csvimport;

import java.util.ArrayList;
import java.util.List;

/**
 * CsvImportService class.
 */
public class CsvImportService {

    private final CustomerStore store;
    private final AuditLog auditLog;
    private int count = 0;

    /**
     * Constructor.
     *
     * @param store    the store
     * @param auditLog the audit log
     */
    public CsvImportService(CustomerStore store, AuditLog auditLog) {
        this.store = store;
        this.auditLog = auditLog;
    }

    /**
     * Process the csv.
     *
     * @param csvText the csv text
     * @param flag    the flag
     * @return the import result
     */
    public ImportResult process(String csvText, boolean flag) {
        List<String> listErrors = new ArrayList<>();
        int intImported = 0;
        int intSkipped = 0;
        boolean hasHeader = false;
        // Excel exports start with a byte order mark, which would otherwise end up inside the first email
        if (csvText.startsWith("﻿")) {
            csvText = csvText.substring(1);
        }
        String[] arr = csvText.split("\r?\n");
        if (arr.length > 0) {
            if (arr[0].toLowerCase().startsWith("email")) {
                hasHeader = true;
            }
        }
        // loop through the lines
        for (int i = 0; i < arr.length; i++) {
            String strLine = arr[i];
            if (strLine != null) {
                if (!ImportHelper.isNullOrEmpty(strLine)) {
                    if (!(i == 0 && hasHeader)) {
                        String[] parts = strLine.split(",");
                        if (parts.length >= 3) {
                            String s = parts[0].trim().toLowerCase();
                            String n = parts[1].trim();
                            String t = parts[2].trim();
                            if (s.contains("@") && s.indexOf("@") > 0 && s.indexOf("@") < s.length() - 1) {
                                int tier = t.equals("gold") ? 3 : t.equals("silver") ? 2 : t.equals("bronze") ? 1 : 0;
                                if (tier != 0) {
                                    try {
                                        // The auditors require an entry for every attempt, so this is written before the save, not after it
                                        auditLog.record("import " + s);
                                        Customer customer = new Customer(s, n, tier, tier == 3 ? 365 : 90);
                                        if (store.exists(s)) {
                                            if (flag) {
                                                store.save(customer);
                                                intImported++;
                                            } else {
                                                intSkipped++;
                                            }
                                        } else {
                                            store.save(customer);
                                            intImported++;
                                        }
                                    } catch (Exception e) {
                                        // do nothing
                                    }
                                } else {
                                    listErrors.add("line " + (i + 1) + ": unknown tier " + t);
                                }
                            } else {
                                listErrors.add("line " + (i + 1) + ": bad email");
                            }
                        } else {
                            listErrors.add("line " + (i + 1) + ": expected 3 columns");
                        }
                    }
                }
            }
        }
        // count = count + intImported + intSkipped;
        count = count + intImported;
        ImportResult result = new ImportResult(intImported, intSkipped, listErrors);
        return result;
    }

    /**
     * Gets the count.
     *
     * @return the count
     */
    public int getCount() {
        int result = count;
        count = 0;
        return result;
    }
}
