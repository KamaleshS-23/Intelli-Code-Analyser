package demo;

/**
 * Public API without method-level Javadoc.
 */
public class AuthManager {

    public boolean validateOAuthToken(String token, String clientId) {
        if (token == null || clientId == null) {
            return false;
        }
        return token.length() > 10 && clientId.length() > 2;
    }
}
