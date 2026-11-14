export type OrderLine = { sku: string; unitPriceCents: number; quantity: number };
export type Order = { customerId: string; lines: OrderLine[]; couponPercent?: number };
export type Quote = { subtotalCents: number; discountCents: number; taxCents: number; totalCents: number };
