package com.example.csvimport;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

// Golden-master driver: prints what CsvImportService does for each case, so the scenario recorder can lock it.
public class CharacterizationDriver {

    private static final String BYTE_ORDER_MARK = "﻿";

    // Records every call in order, because the audit entry must come before the save.
    static final class RecordingStore implements CustomerStore, AuditLog {
        final List<String> events = new ArrayList<>();
        final Set<String> existingEmails = new HashSet<>();
        final Set<String> emailsThatFailToSave = new HashSet<>();

        public boolean exists(String email) {
            events.add("exists " + email);
            return existingEmails.contains(email);
        }

        public void save(Customer customer) {
            events.add("save " + customer);
            if (emailsThatFailToSave.contains(customer.email())) {
                throw new IllegalStateException("store refused " + customer.email());
            }
            existingEmails.add(customer.email());
        }

        public void record(String entry) {
            events.add("audit " + entry);
        }
    }

    public static void main(String[] arguments) {
        String caseGroup = 0 == arguments.length ? "all" : arguments[0];
        if ("all".equals(caseGroup) || "rows".equals(caseGroup)) {
            printCase("header and tiers", "email,name,tier\nada@example.com,Ada,gold\nbo@example.com,Bo,silver\ncy@example.com,Cy,bronze", false, new RecordingStore());
            printCase("no header", "ada@example.com,Ada,gold", false, new RecordingStore());
            printCase("header in capitals", "EMAIL,NAME,TIER\nada@example.com,Ada,gold", false, new RecordingStore());
            printCase("byte order mark", BYTE_ORDER_MARK + "email,name,tier\nada@example.com,Ada,gold", false, new RecordingStore());
            printCase("windows line endings", "email,name,tier\r\nada@example.com,Ada,gold\r\nbo@example.com,Bo,silver\r\n", false, new RecordingStore());
            printCase("email lower cased and fields trimmed", "  Ada@Example.COM , Ada Lovelace ,  gold ", false, new RecordingStore());
            printCase("blank and whitespace lines", "\n   \nada@example.com,Ada,gold\n\n", false, new RecordingStore());
            printCase("control character and unicode space lines", "\u0001\n\u2003\nada@example.com,Ada,gold", false, new RecordingStore());
            printCase("extra columns", "ada@example.com,Ada,gold,ignored,also", false, new RecordingStore());
            printCase("empty name", "ada@example.com,,bronze", false, new RecordingStore());
            printCase("empty input", "", false, new RecordingStore());
            printCase("header only", "email,name,tier", false, new RecordingStore());
        }
        if ("all".equals(caseGroup) || "errors".equals(caseGroup)) {
            printCase("too few columns", "email,name,tier\nada@example.com,Ada", false, new RecordingStore());
            printCase("bad emails", "@example.com,A,gold\nada@,B,gold\nada.example.com,C,gold\na@b,D,gold", false, new RecordingStore());
            printCase("unknown tier", "ada@example.com,Ada,platinum\nbo@example.com,Bo,Gold", false, new RecordingStore());
            printCase("quoted comma splits the row (known bug)", "jo@example.com,\"Smith, Jo\",gold", false, new RecordingStore());
            printCase("first data row looks like a header", "emailer@example.com,Em,gold\nada@example.com,Ada,gold", false, new RecordingStore());
        }
        if ("all".equals(caseGroup) || "store".equals(caseGroup)) {
            RecordingStore storeWithExisting = new RecordingStore();
            storeWithExisting.existingEmails.add("old@example.com");
            printCase("existing customer skipped", "old@example.com,Old,silver\nnew@example.com,New,gold", false, storeWithExisting);
            RecordingStore storeToOverwrite = new RecordingStore();
            storeToOverwrite.existingEmails.add("old@example.com");
            printCase("existing customer overwritten", "old@example.com,Old,silver\nnew@example.com,New,gold", true, storeToOverwrite);
            RecordingStore failingStore = new RecordingStore();
            failingStore.emailsThatFailToSave.add("bad@example.com");
            printCase("failed save is swallowed (known bug)", "bad@example.com,Bad,gold\nok@example.com,Ok,silver", false, failingStore);
            printCase("duplicate rows in one file", "ada@example.com,Ada,gold\nada@example.com,Ada Again,silver", false, new RecordingStore());
            printCountBehavior();
        }
    }

    private static void printCase(String caseName, String csvText, boolean isOverwriteAllowed, RecordingStore store) {
        CsvImportService service = new CsvImportService(store, store);
        System.out.println("== " + caseName + (isOverwriteAllowed ? " (overwrite)" : ""));
        try {
            System.out.println("result " + service.process(csvText, isOverwriteAllowed));
        } catch (RuntimeException failure) {
            System.out.println("threw " + failure);
        }
        store.events.forEach(event -> System.out.println("  " + event));
    }

    // getCount resets the count as it reads it; pinned as current behavior.
    private static void printCountBehavior() {
        RecordingStore store = new RecordingStore();
        CsvImportService service = new CsvImportService(store, store);
        service.process("a@example.com,A,gold\nb@example.com,B,silver", false);
        store.existingEmails.add("c@example.com");
        service.process("c@example.com,C,gold\nd@example.com,D,bronze", false);
        System.out.println("== count");
        System.out.println("count " + service.getCount() + " then " + service.getCount());
    }
}
