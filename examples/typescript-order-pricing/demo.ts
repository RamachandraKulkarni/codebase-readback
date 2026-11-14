import { formatQuote, quoteOrder } from "./src/index.ts";

const orders = [
  { customerId: "C-1", lines: [{ sku: "pen", unitPriceCents: 250, quantity: 4 }] },
  { customerId: "ACME", lines: [{ sku: "desk", unitPriceCents: 45000, quantity: 1 }] },
  { customerId: "C-2", lines: [{ sku: "chair", unitPriceCents: 12000, quantity: 10 }], couponPercent: 10 },
  { customerId: "C-3", lines: [{ sku: "lamp", unitPriceCents: 3000, quantity: 1 }], couponPercent: 150 },
];
for (const order of orders) {
  console.log(`${order.customerId}\n${formatQuote(quoteOrder(JSON.stringify(order)))}\n`);
}
