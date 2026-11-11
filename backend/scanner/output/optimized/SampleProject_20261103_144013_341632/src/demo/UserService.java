package demo;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

/**
 * Intentionally smell-heavy sample
 */
public class UserService {

    private String dbPassword = System.getenv("DB_PASSWORD");

    public List<String> getUsers() throws IOException {
        List<String> users = new ArrayList<>();
        return users;
    }
}