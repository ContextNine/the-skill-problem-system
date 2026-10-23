const addresses = {
  horizon_years: "'Global Assumptions'!C6",
  inflation: "'Global Assumptions'!C8",
  tax_band_growth: "'Global Assumptions'!C9",
  revenue_monthly: "'Global Assumptions'!C15",
  revenue_growth: "'Global Assumptions'!C16",
  operating_costs_monthly: "'Global Assumptions'!C17",
  operating_cost_growth: "'Global Assumptions'!C18",
  personal_spending_monthly: "'Global Assumptions'!C29",
  personal_spending_growth: "'Global Assumptions'!C30",
  partner_savings: "'Global Assumptions'!C31",
  cash_return: "'Global Assumptions'!C32",
  goalsave_return: "'Global Assumptions'!C42",
  goalsave_cap: "'Global Assumptions'!C43",
  tfsa_return: "'Global Assumptions'!C44",
  tfsa_annual_limit: "'Global Assumptions'!C45",
  tfsa_lifetime_limit: "'Global Assumptions'!C46",
  ra_return: "'Global Assumptions'!C48",
  taxable_total_return: "'Global Assumptions'!C53",
  taxable_dividend_yield: "'Global Assumptions'!C54",
  taxable_capital_growth: "'Global Assumptions'!C55",
  disa_value: "'Global Assumptions'!C62",
  disa_selling_cost: "'Global Assumptions'!C66",
  disa_owner_cost_monthly: "'Global Assumptions'!C67",
  disa_rent_monthly: "'Global Assumptions'!C68",
  disa_vacancy: "'Global Assumptions'!C69",
  disa_management: "'Global Assumptions'!C70",
  disa_maintenance: "'Global Assumptions'!C71",
  disa_growth: "'Global Assumptions'!C72",
  gp_rent_monthly: "'Global Assumptions'!C74",
  housing_cost_growth: "'Global Assumptions'!C75",
  buy_year: "'Global Assumptions'!C80",
  buy_price: "'Global Assumptions'!C81",
  deposit_pct: "'Global Assumptions'!C82",
  mortgage_rate: "'Global Assumptions'!C83",
  mortgage_term: "'Global Assumptions'!C84",
  other_purchase_cost_pct: "'Global Assumptions'!C85",
  home_owner_cost_pct: "'Global Assumptions'!C86",
  home_growth: "'Global Assumptions'!C87",
  affordability_pct: "'Global Assumptions'!C88",
}

const edits = input.edits || {}
const keys = Object.keys(edits)
if (keys.length === 0) throw new Error("input.edits must contain at least one supported assumption")

const unknown = keys.filter((key) => !(key in addresses))
if (unknown.length) throw new Error(`Unsupported assumptions: ${unknown.join(", ")}`)

const previous = {}
for (const key of keys) previous[key] = (await xlsx.readCell(wb, addresses[key])).text

const source = input.source || "User instruction"
const asOf = input.as_of || "date not supplied"
const cells = keys.map((key) => ({
  address: addresses[key],
  value: edits[key],
  note: { text: `Source: ${source}, ${asOf}. Updated through spreadsheets-housing-decision-model skill.` },
}))

const result = await xlsx.setCells(wb, cells)
if (result.errors.length) return { previous, editedInputs: cells.map((cell) => cell.address), errors: result.errors }

const total = Number((await xlsx.readCell(wb, addresses.taxable_total_return)).value)
const dividend = Number((await xlsx.readCell(wb, addresses.taxable_dividend_yield)).value)
const growth = Number((await xlsx.readCell(wb, addresses.taxable_capital_growth)).value)
if (Math.abs(total - dividend - growth) > 1e-9) {
  throw new Error("Taxable total return must equal dividend yield plus capital growth")
}

const outputs = [
  "Dashboard!B4",
  "Dashboard!B7", "Dashboard!C7", "Dashboard!D7", "Dashboard!E7", "Dashboard!P7",
  "Dashboard!B8", "Dashboard!C8", "Dashboard!D8", "Dashboard!E8", "Dashboard!P8",
  "Dashboard!B9", "Dashboard!C9", "Dashboard!D9", "Dashboard!E9", "Dashboard!P9",
  "Dashboard!B10", "Dashboard!D10", "Dashboard!E10", "Dashboard!P10",
  "Dashboard!B11", "Dashboard!D11", "Dashboard!E11", "Dashboard!P11",
  "Dashboard!B12", "Dashboard!D12", "Dashboard!E12", "Dashboard!P12",
]
const outputValues = Object.fromEntries(outputs.map((address) => [address, result.touched[address] ?? null]))
const current = Object.fromEntries(keys.map((key) => [key, result.touched[addresses[key]] ?? null]))

return {
  previous,
  current,
  outputValues,
  editedInputs: cells.map((cell) => cell.address),
  downstreamChangedCount: result.changed.length,
  errors: result.errors,
}
