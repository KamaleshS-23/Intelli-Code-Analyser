package demo;

/**
 * Deliberately envies Customer instead of living on Customer.
 */
public class InvoiceService {

    public double calculateCustomerDiscount(Customer customer) {
        double discount = 0;
        if (customer.getName() != null && customer.getName().length() > 0) {
            discount += 1;
        }
        if (customer.getLoyaltyPoints() > 100) {
            discount += 2;
        }
        if (customer.isPremium()) {
            discount += 3;
        }
        if (customer.getLifetimeSpend() > 5000) {
            discount += 4;
        }
        if (customer.hasHighLoyalty()) {
            discount += 5;
        }
        if (customer.getLoyaltyPoints() > 2000 && customer.isPremium()) {
            discount += 2;
        }
        if (customer.getLifetimeSpend() > 10000) {
            discount += customer.getLoyaltyPoints() * 0.01;
        }
        return discount;
    }
}
