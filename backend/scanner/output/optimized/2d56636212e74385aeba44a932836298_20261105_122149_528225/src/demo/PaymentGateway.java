package demo;

/**
 * Generic exception handling sample.
 */
public class PaymentGateway {

    public boolean chargeCard(String cardNumber, int amount) {
        try {
            if (cardNumber == null || amount <= 0) {
                throw new IllegalArgumentException("invalid charge");
            }
            return amount < 100000;
        } catch (Exception e) {
            return false;
        }
    }
}
