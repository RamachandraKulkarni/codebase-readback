package com.example.csvimport;

/**
 * Helper class for the import.
 */
public class ImportHelper {

    /**
     * Checks if the string is null or empty.
     *
     * @param s the string
     * @return true if the string is null or empty
     */
    public static boolean isNullOrEmpty(String s) {
        if (s == null) {
            return true;
        } else {
            if (s.trim().length() == 0) {
                return true;
            } else {
                return false;
            }
        }
    }
}
