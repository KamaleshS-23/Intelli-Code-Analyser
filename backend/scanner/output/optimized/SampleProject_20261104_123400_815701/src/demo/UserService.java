package demo;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

/**
 * Intentionally smell-heavy sample used by the technical debt agent demos.
 */
public class UserService {

    private String currentUser;
    private String currentPassword;
    private String currentToken;
    private List<String> loginHistory = new ArrayList<>();
    private AuditLogService auditLogService = new AuditLogService();

    // Unused field on purpose.
    private String unusedCacheKey;

    public String login(String username, String password, String ipAddress, boolean rememberMe) {
        String tempToken = username + "-temp";
        if (username == null || username.isEmpty()) {
            System.out.println("Username is required");
            return null;
        }
        if (password == null || password.length() < 8) {
            System.out.println("Password must be at least 8 characters");
            return null;
        }
        currentUser = username;
        currentPassword = password;

        boolean authenticated = false;
        if (currentPassword.equals(password)) {
            authenticated = true;
        }
        if (!authenticated) {
            System.out.println("Authentication failed for " + username);
            return null;
        }

        String token = username + ":" + System.currentTimeMillis();
        currentToken = token;
        auditLogService.recordLogin(username);

        System.out.println("Sending login notification email to " + username);
        System.out.println("Login detected from IP: " + ipAddress);
        loginHistory.add(username + " logged in from " + ipAddress);

        if (rememberMe) {
            System.out.println("Extending session for " + username);
        }

        return token;
    }

    public void connectDatabase() {
        String dbPassword = "SuperSecret123!";
        System.out.println("Connecting with password length " + dbPassword.length());
    }

    public boolean processPayment(String card, int amount, boolean express, boolean refundable,
                                  boolean international, String currency, String merchant) {
        if (card == null) {
            return false;
        }
        if (amount <= 0) {
            return false;
        }
        if (express && international) {
            return amount > 100 && currency != null;
        }
        if (refundable || merchant == null) {
            return false;
        }
        if (currency.equals("USD") || currency.equals("EUR") || currency.equals("INR")) {
            if (amount > 50 && amount < 5000) {
                if (card.length() > 12 && card.length() < 20) {
                    return true;
                }
            }
        }
        if (amount == 9999) {
            return true;
        }
        return amount % 7 == 0 && merchant.length() > 3;
    }

    public String createUserProfile(String first, String last, String email, String phone,
                                    String city, String country, String role) {
        return first + " " + last + " <" + email + "> " + phone + " " + city + "/" + country + " " + role;
    }

    public boolean verifyUserSession(String token, String user, boolean admin) {
        if (token != null) {
            if (token.length() > 5) {
                if (user != null) {
                    if (user.length() > 2) {
                        if (admin || user.equals(currentUser)) {
                            return true;
                        }
                    }
                }
            }
        }
        return false;
    }

    public void loadConfig() {
        try {
            if (currentUser == null) {
                throw new IOException("missing user");
            }
        } catch (IOException e) {
        }
    }

    public int calculateTimeout(int days) {
        return days * 86400;
    }

    private boolean oldValidateToken(String token) {
        return token != null && token.contains(":");
    }

    public boolean registerUser(String username, String password) {
        if (username == null || username.isEmpty()) {
            return false;
        }
        if (password == null || password.length() < 8) {
            return false;
        }
        currentUser = username;
        currentPassword = password;
        System.out.println("User registered: " + username);
        return true;
    }

    public boolean registerAdmin(String username, String password) {
        if (username == null || username.isEmpty()) {
            return false;
        }
        if (password == null || password.length() < 8) {
            return false;
        }
        currentUser = username;
        currentPassword = password;
        System.out.println("User registered: " + username);
        return true;
    }

    public String getCurrentUser() {
        return currentUser;
    }

    public String getCurrentToken() {
        return currentToken;
    }

    public List<String> getLoginHistory() {
        return loginHistory;
    }
}
