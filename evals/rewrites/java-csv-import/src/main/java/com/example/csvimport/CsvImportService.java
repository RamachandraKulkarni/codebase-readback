package com.example.csvimport;

import java.util.ArrayList;
import java.util.List;

public class CsvImportService {

    private static final String BYTE_ORDER_MARK = "﻿";
    private static final int REQUIRED_COLUMN_COUNT = 3;
    private static final int GOLD_TIER = 3;
    private static final int SILVER_TIER = 2;
    private static final int BRONZE_TIER = 1;
    private static final int UNKNOWN_TIER = 0;
    private static final int GOLD_RETENTION_DAYS = 365;
    private static final int STANDARD_RETENTION_DAYS = 90;

    private enum ImportOutcome { IMPORTED, SKIPPED, FAILED }

    private final CustomerStore store;
    private final AuditLog auditLog;
    private int importedSinceLastCount = 0;

    public CsvImportService(CustomerStore store, AuditLog auditLog) {
        this.store = store;
        this.auditLog = auditLog;
    }

    public ImportResult process(String csvText, boolean replaceExistingCustomers) {
        String[] lines = removeByteOrderMark(csvText).split("\r?\n");
        boolean hasHeader = lines[0].toLowerCase().startsWith("email");
        List<String> errors = new ArrayList<>();
        int importedCount = 0;
        int skippedCount = 0;
        for (int lineIndex = hasHeader ? 1 : 0; lineIndex < lines.length; lineIndex++) {
            String line = lines[lineIndex];
            // trim, not isBlank: they disagree on control characters and Unicode spaces.
            if (line.trim().isEmpty()) {
                continue;
            }
            String linePrefix = "line " + (lineIndex + 1) + ": ";
            String[] columns = line.split(",");
            if (columns.length < REQUIRED_COLUMN_COUNT) {
                errors.add(linePrefix + "expected 3 columns");
                continue;
            }
            String email = columns[0].trim().toLowerCase();
            String name = columns[1].trim();
            String tierName = columns[2].trim();
            if (!isPlausibleEmail(email)) {
                errors.add(linePrefix + "bad email");
                continue;
            }
            int tier = tierFromName(tierName);
            if (UNKNOWN_TIER == tier) {
                errors.add(linePrefix + "unknown tier " + tierName);
                continue;
            }
            int retentionDays = GOLD_TIER == tier ? GOLD_RETENTION_DAYS : STANDARD_RETENTION_DAYS;
            ImportOutcome outcome = importCustomer(new Customer(email, name, tier, retentionDays), replaceExistingCustomers);
            if (ImportOutcome.IMPORTED == outcome) {
                importedCount++;
            } else if (ImportOutcome.SKIPPED == outcome) {
                skippedCount++;
            }
        }
        importedSinceLastCount += importedCount;
        return new ImportResult(importedCount, skippedCount, errors);
    }

    // Reported, kept: reading the count also resets it to zero.
    public int getCount() {
        int importedCount = importedSinceLastCount;
        importedSinceLastCount = 0;
        return importedCount;
    }

    private ImportOutcome importCustomer(Customer customer, boolean replaceExistingCustomers) {
        try {
            // The auditors require an entry for every attempt, so this is written before the save, not after it
            auditLog.record("import " + customer.email());
            if (store.exists(customer.email()) && !replaceExistingCustomers) {
                return ImportOutcome.SKIPPED;
            }
            store.save(customer);
            return ImportOutcome.IMPORTED;
        } catch (Exception swallowedFailure) {
            // Reported, kept: a failed save is not imported, not skipped and not listed as an error.
            return ImportOutcome.FAILED;
        }
    }

    private static String removeByteOrderMark(String csvText) {
        // Excel exports start with a byte order mark, which would otherwise end up inside the first email
        return csvText.startsWith(BYTE_ORDER_MARK) ? csvText.substring(1) : csvText;
    }

    private static boolean isPlausibleEmail(String email) {
        int atSignIndex = email.indexOf('@');
        return 0 < atSignIndex && atSignIndex < email.length() - 1;
    }

    private static int tierFromName(String tierName) {
        return switch (tierName) {
            case "gold" -> GOLD_TIER;
            case "silver" -> SILVER_TIER;
            case "bronze" -> BRONZE_TIER;
            default -> UNKNOWN_TIER;
        };
    }
}
