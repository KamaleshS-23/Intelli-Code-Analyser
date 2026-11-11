package demo;

/**
 * Circular partner for UserService.
 */
public class AuditLogService {

    private UserService userService = new UserService();

    public void recordLogin(String username) {
        System.out.println("Audit login for " + username + " current=" + userService.getCurrentUser());
    }
}
