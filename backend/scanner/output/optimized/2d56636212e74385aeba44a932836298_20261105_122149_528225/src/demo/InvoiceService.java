package demo;

/**
 * Deliberately envies Customer instead of living on Customer.
 */
public class InvoiceService {

    public double calculateCustomerDiscount(Customer customer) {
        double discount = 0;
        discount += getNameDiscount(customer);
        discount += getLoyaltyPointsDiscount(customer);
        discount += getPremiumDiscount(customer);
        discount += getLifetimeSpendDiscount(customer);
        discount += getHighLoyaltyDiscount(customer);
        discount += getBonusLoyaltyDiscount(customer);
        discount += getLifetimeBonusDiscount(customer);
        return discount;
    }

    private double getNameDiscount(Customer customer) {
        return (customer.getName() != null && !customer.getName().isEmpty()) ? 1 : 0;
    }

    private double getLoyaltyPointsDiscount(Customer customer) {
        return (customer.getLoyaltyPoints() > 100) ? 2 : 0;
    }

    private double getPremiumDiscount(Customer customer) {
        return customer.isPremium() ? 3 : 0;
    }

    private double getLifetimeSpendDiscount(Customer customer) {
        return (customer.getLifetimeSpend() > 5000) ? 4 : 0;
    }

    private double getHighLoyaltyDiscount(Customer customer) {
        return customer.hasHighLoyalty() ? 5 : 0;
    }

    private double getBonusLoyaltyDiscount(Customer customer) {
        return (customer.getLoyaltyPoints() > 2000 && customer.isPremium()) ? 2 : 0;
    }

    private double getLifetimeBonusDiscount(Customer customer) {
        return (customer.getLifetimeSpend() > 10000) ? (customer.getLoyaltyPoints() * 0.01) : 0;
    }
}