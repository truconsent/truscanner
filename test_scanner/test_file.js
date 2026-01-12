// Test file for scanner - should detect actual personal data, not false positives

// This should be detected - actual email value
const userEmail = "john.doe@example.com";
const contactEmail = "support@company.com";

// This should be detected - actual phone number
const phoneNumber = "+1-555-123-4567";
const mobile = "9876543210";

// This should be detected - actual name
const firstName = "John";
const lastName = "Doe";
const fullName = "John Doe";

// This should be detected - actual address
const homeAddress = "123 Main Street, New York, NY 10001";

// This should be detected - actual date of birth
const dateOfBirth = "1990-01-15";
const dob = "01/15/1990";

// These should NOT be detected - just variable names, not actual data
function getUserEmail(email) {
    return email;
}

const emailField = "email";
const phoneField = "phone";
const nameField = "name";

// Database query - field names should not be detected
const query = "SELECT name, email, phone FROM users";

// HTML/CSS - should not be detected
const html = '<meta name="viewport" content="width=device-width">';
const css = 'font-family: "Google Fonts"';
const icon = '<link rel="apple-touch-icon" href="/icon.png">';

// Comments - should not be detected
// User email: test@example.com
/* Contact phone: 555-1234 */

// Object structure - field names should not be detected
const user = {
    name: "",
    email: "",
    phone: ""
};

// Function parameters - should not be detected
function createUser(name, email, phone) {
    return { name, email, phone };
}

// Should be detected - actual SSN
const ssn = "123-45-6789";

// Should be detected - actual credit card (for testing)
const cardNumber = "4532-1234-5678-9010";

// Should be detected - actual IP address
const ipAddress = "192.168.1.1";

