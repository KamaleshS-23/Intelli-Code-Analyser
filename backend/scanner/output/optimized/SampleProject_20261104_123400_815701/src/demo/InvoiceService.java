package demo;

/**
 * Deliberately envies Customer instead of living on Customer.
 */
public class InvoiceService {

    public double calculateCustomerDiscount(Customer customer) {
        double discount = 0;
        discount += getBaseDiscount(customer);
        discount += getLoyaltyDiscount(customer);
        discount += getPremiumDiscount(customer);
        discount += getSpendDiscount(customer);
        return discount;
    }

    private double getBaseDiscount(Customer customer) {
        double discount = 0;
        if (customer.getName() != null && !customer.getName().isEmpty()) {
            discount += 1;
        }
        return discount;
    }

    private double getLoyaltyDiscount(Customer customer) {
        double discount = 0;
        if (customer.getLoyaltyPoints() > 100) {
            discount += 2;
        }
        if (customer.hasHighLoyalty()) {
            discount += 5;
        }
        return discount;
    }

    private double getPremiumDiscount(Customer customer) {
        double discount = 0;
        if (customer.isPremium()) {
            discount += 3;
            if (customer.getLoyaltyPoints() > 2000) {
                discount += 2;
            }
        }
        return discount;
    }

    private double getSpendDiscount(Customer customer) {
        double discount = 0;
        if (customer.getLifetimeSpend() > 5000) {
            discount += 4;
        }
        if (customer.getLifetimeSpend() > 10000) {
            discount += customer.getLoyaltyPoints() * 0.01;
        }
        return discount;
    }
}