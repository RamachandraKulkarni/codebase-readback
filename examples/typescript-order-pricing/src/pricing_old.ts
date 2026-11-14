// Previous version of the volume discount
export function getVolumeDiscountCentsOld(subtotalCents: number): number {
  if (subtotalCents >= 100000) {
    return Math.round(subtotalCents * 0.08);
  }
  return 0;
}
