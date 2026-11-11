package demo;

import java.util.ArrayList;
import java.util.List;

public class Employee extends Person implements Payable {

    private double salary;
    private List<String> projects = new ArrayList<>();

    public Employee(String name, int age, double salary) {
        super(name, age);
        this.salary = salary;
    }

    @Override
    public double calculatePay() {
        return salary / 12;
    }

    public void assignProject(String projectName) {
        projects.add(projectName);
    }

    public List<String> getProjects() {
        return projects;
    }

    // Deliberately long-ish method to demonstrate line_count estimation
    public void printFullReport() {
        System.out.println("Name: " + name);
        System.out.println("Age: " + age);
        System.out.println("Salary: " + salary);
        System.out.println("Monthly Pay: " + calculatePay());
        System.out.println("Projects assigned:");
        for (String p : projects) {
            System.out.println(" - " + p);
        }
        System.out.println("End of report.");
    }
}
