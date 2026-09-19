# E-Shop Checkout Requirements

## 1. Product Catalogue

### REQ-001 - Product Display
The checkout page shall display the following products:

- T-shirt priced at $20.00
- Mug priced at $8.00
- Cap priced at $12.00

Each product shall have an Add to Cart button.

---

## 2. Shopping Cart

### REQ-002 - Quantity Selection
The checkout page shall provide a quantity field for each product.

Each quantity shall default to 0 and shall not accept values below 0.

### REQ-003 - Cart Total Calculation
The application shall calculate the cart total using the following prices:

- T-shirt: $20.00 per item
- Mug: $8.00 per item
- Cap: $12.00 per item

The displayed cart total shall update when a product quantity changes.

The total shall be displayed using two decimal places.

Example:

2 T-shirts + 1 Mug + 1 Cap

Total = (2 × 20) + (1 × 8) + (1 × 12)

Total = $60.00

---

## 3. Discount Code

### REQ-004 - Empty Discount Code
If the user attempts to apply a discount without entering a code, the application shall display:

"Enter a code"

### REQ-005 - Valid Discount Code
The application shall recognize the discount code:

SAVE15

When SAVE15 is applied, the application shall calculate a 15% discount on the current cart total.

The application shall display:

"15% applied. New total: $<discounted amount>"

The discounted amount shall be displayed using two decimal places.

### REQ-006 - Invalid Discount Code
If the entered discount code is not SAVE15, the application shall display:

"Invalid code"

---

## 4. Customer Information

### REQ-007 - Customer Name
The customer name field is required.

If the user attempts to pay without providing a name, the application shall display:

"Required"

### REQ-008 - Customer Email
The customer email field is required.

The application shall validate that the email follows a basic email format.

If the email is missing or invalid, the application shall display:

"Invalid email"

### REQ-009 - Customer Address
The customer address field is required.

If the user attempts to pay without providing an address, the application shall display:

"Required"

---

## 5. Shipping Method

### REQ-010 - Shipping Selection
The user shall be able to select one of the following shipping methods:

- Standard
- Express

Standard shipping shall be selected by default.

---

## 6. Payment Method

### REQ-011 - Payment Selection
The user shall be able to select one of the following payment methods:

- Credit Card
- PayPal

Credit Card shall be selected by default.

---

## 7. Checkout Validation

### REQ-012 - Successful Payment
When the customer provides:

- a non-empty name,
- a valid email address,
- and a non-empty address,

and selects Pay Now, the application shall display:

"Payment Successful!"

### REQ-013 - Failed Validation
If one or more required customer fields are invalid, the application shall not display the successful payment message.

Instead, validation messages shall be displayed beside the invalid fields.