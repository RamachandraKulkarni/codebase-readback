package com.example.csvimport;

import java.util.HashMap;
import java.util.Map;

public class Demo {

    public static void main(String[] args) {
        Map<String, Customer> saved = new HashMap<>();
        saved.put("old@example.com", new Customer("old@example.com", "Old Name", 1, 90));
        CustomerStore store = new CustomerStore() {
            public boolean exists(String email) {
                return saved.containsKey(email);
            }

            public void save(Customer customer) {
                if (customer.name().isEmpty()) {
                    throw new IllegalStateException("name is required");
                }
                saved.put(customer.email(), customer);
            }
        };
        CsvImportService service = new CsvImportService(store, entry -> System.out.println("audit: " + entry));
        String csv = "﻿email,name,tier\nAda@Example.com,Ada,gold\nold@example.com,New Name,silver\n\nnot-an-email,Bob,gold\n"
                + "eve@example.com,Eve,platinum\nshort,row\nnoname@example.com,,bronze\njo@example.com,\"Smith, Jo\",gold";
        System.out.println(service.process(csv, false));
        System.out.println(service.process(csv, true));
        System.out.println("count " + service.getCount() + " then " + service.getCount());
        System.out.println(saved.get("old@example.com"));
    }
}
