const dashboard = await xlsx.readRangeTsv(
  wb,
  { sheet: "Dashboard", from: { row: 4, col: 1 }, to: { row: 24, col: 17 } },
  { includeFormulas: true },
)

const assumptions = await xlsx.readRangeTsv(
  wb,
  { sheet: "Global Assumptions", from: { row: 6, col: 1 }, to: { row: 90, col: 5 } },
  { includeFormulas: true },
)

const optimizer = await xlsx.readRangeTsv(
  wb,
  { sheet: "Tax Optimizer", from: { row: 4, col: 1 }, to: { row: 10, col: 9 } },
  { includeFormulas: true },
)

const maxHousingRatios = await xlsx.evaluateFormulas(wb, "Annual Model", [
  "=MAX(BR5:BR45)",
  "=MAX(BR48:BR88)",
  "=MAX(BR91:BR131)",
  "=MAX(BR134:BR174)",
  "=MAX(BR177:BR217)",
  "=MAX(BR220:BR260)",
])

return { dashboard, assumptions, optimizer, maxHousingRatios }
