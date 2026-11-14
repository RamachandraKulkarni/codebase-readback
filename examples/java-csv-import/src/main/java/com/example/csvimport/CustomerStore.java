package com.example.csvimport;

public interface CustomerStore {
    boolean exists(String email);

    void save(Customer customer);
}
