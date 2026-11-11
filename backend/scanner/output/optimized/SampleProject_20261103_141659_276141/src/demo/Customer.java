package demo;

/**
 * Customer data used to demonstrate Feature Envy.
 */
public class Customer {

    private String name;
    private int loyaltyPoints;
    private boolean premium;
    private double lifetimeSpend;

    public Customer(String name, int loyaltyPoints, boolean premium, double lifetimeSpend) {
        this.name = name;
        this.loyaltyPoints = loyaltyPoints;
        this.premium = premium;
        this.lifetimeSpend = lifetimeSpend;
    }

    public String getName() {
        return name;
    }

    public int getLoyaltyPoints() {
        return loyaltyPoints;
    }

    public boolean isPremium() {
        return premium;
    }

    public double getLifetimeSpend() {
        return lifetimeSpend;
    }

    public boolean hasHighLoyalty() {
        return loyaltyPoints > 1000;
    }
}
