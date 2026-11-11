package demo;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

/**
 * Intentionally smell-heavy sample used by the technical debt agent demos.
 */
public class UserService {

    public static class UserProfileRequest {
        public String first;
        public String last;
        public String email;
        public String phone;
        public String city;
        public String country;
        public String role;

        public UserProfileRequest(String first, String last, String email, String phone, String city, String country, String role) {
            this.first = first;
            this.last = last;
            this.email = email;
            this.phone = phone;
            this.city = city;
            this.country = country;
            this.role = role;
        }
    }

    private String currentUser;
    private String currentPassword;
    private String currentToken;
    private List<String> loginHistory = new ArrayList<>();
    private AuditLogService auditLogService = new AuditLogService();

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
        if (card == null || amount <= 0) return false;
        if (express && international) return amount > 100 && currency != null;
        if (refundable || merchant == null) return false;
        if (isValidCurrencyAmount(currency, amount) && isValidCard(card)) return true;
        if (amount == 9999) return true;
        return amount % 7 == 0 && merchant.length() > 3;
    }

    private boolean isValidCurrencyAmount(String currency, int amount) {
        if (currency == null) return false;
        boolean validCurrency = currency.equals("USD") || currency.equals("EUR") || currency.equals("INR");
        return validCurrency && amount > 50 && amount < 5000;
    }

    private boolean isValidCard(String card) {
        return card.length() > 12 && card.length() < 20;
    }

    public String createUserProfile(UserProfileRequest request) {
        return request.first + " " + request.last + " <" + request.email + "> " + request.phone + " " + request.city + "/" + request.country + " " + request.role;
    }

    public boolean verifyUserSession(String token, String user, boolean admin) {
        if (token == null || token.length() <= 5) return false;
        if (user == null || user.length() <= 2) return false;
        return admin || user.equals(currentUser);
    }

    public void loadConfig() {
        try {
            if (currentUser == null) {
                throw new IOException("User not logged in");
            }
        } catch (IOException e) {
            e