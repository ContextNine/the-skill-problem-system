# Housing decision model reference

## Purpose and ownership

Workbook compares six housing decisions over 40 years using household, company, tax, investment, and property wealth. Only target workbook may change. User owns all inputs and decision trade-offs.

Canonical source is live workbook. Values below are snapshot after user-directed update on 2026-07-19. If workbook differs, report drift and use live cells.

## Scenarios

| Dashboard row | Annual Model rows | Code | Decision |
|---|---|---|---|
| 7 | 5:45 | `STAY` | Stay in Disa |
| 8 | 48:88 | `KEEP_RENT` | Rent Green Point; retain and rent Disa |
| 9 | 91:131 | `SELL_RENT` | Sell Disa; rent Green Point forever |
| 10 | 134:174 | `SELL_BUY` | Sell Disa now; rent, then buy |
| 11 | 177:217 | `SELL_ON_BUY` | Rent Disa; sell when buying |
| 12 | 220:260 | `KEEP_BUY` | Retain Disa while buying another home |

Feasibility requires non-negative portfolio/liquidity and maximum housing-cost ratio no higher than 35%. Dashboard rank covers feasible scenarios only.

## Current global assumptions

### Model and business

| Input | Cell | Current value |
|---|---|---:|
| Horizon | `Global Assumptions!C6` | 40 years |
| Inflation | `Global Assumptions!C8` | 6% |
| Tax-band/cap growth | `Global Assumptions!C9` | 6% |
| Revenue | `Global Assumptions!C15` | R100,000/month |
| Revenue growth | `Global Assumptions!C16` | 10% |
| Operating costs | `Global Assumptions!C17` | R10,000/month |
| Operating-cost growth | `Global Assumptions!C18` | 10% |
| Company tax | `Global Assumptions!C19` | 27% |
| Dividends tax | `Global Assumptions!C20` | 20% |
| Company retained-cash return | `Global Assumptions!C21` | 6.5% |
| Terminal operating-profit multiple | `Global Assumptions!C22` | 3x |

Revenue is net of VAT. Matt owns 100%; company share base cost is zero. No partner income is modeled.

### Personal and investments

| Input | Cell | Current value |
|---|---|---:|
| Personal non-housing spending | `Global Assumptions!C29` | R20,000/month |
| Spending growth | `Global Assumptions!C30` | 10% |
| Partner opening savings | `Global Assumptions!C31` | R1,000,000 |
| Cash/legacy return | `Global Assumptions!C32` | 6.5% |
| GoalSave return | `Global Assumptions!C42` | 10% |
| GoalSave modeled contribution cap | `Global Assumptions!C43` | R250,000/person |
| TFSA return | `Global Assumptions!C44` | 11% |
| TFSA annual limit | `Global Assumptions!C45` | R46,000/person |
| TFSA lifetime limit | `Global Assumptions!C46` | R500,000/person |
| RA return | `Global Assumptions!C48` | 11% |
| RA target | `Global Assumptions!C49` | 10% salary |
| Taxable total return | `Global Assumptions!C53` | 12% |
| Dividend yield / capital growth | `Global Assumptions!C54:C55` | 2% / 10% |

Keep taxable total equal to dividend yield plus capital growth. Model applies 20% dividends tax annually and CGT on withdrawals/terminal sale.

### Disa, Green Point, and purchase

| Input | Cell | Current value |
|---|---|---:|
| Disa value / bond | `Global Assumptions!C62:C63` | R1.6m / zero |
| Sell-now CGT / selling costs | `Global Assumptions!C64:C66` | zero / 7.5% |
| Disa owner costs | `Global Assumptions!C67` | R5,000/month |
| Disa rent | `Global Assumptions!C68` | R13,500/month |
| Vacancy / management | `Global Assumptions!C69:C70` | 5% / 0% |
| Maintenance reserve | `Global Assumptions!C71` | 0.5% of value annually |
| Disa property growth | `Global Assumptions!C72` | 9.5% |
| Green Point rent | `Global Assumptions!C74` | R18,000/month |
| Housing-cost growth | `Global Assumptions!C75` | 6% |
| Purchase year / price | `Global Assumptions!C80:C81` | Year 4 / R8m |
| Deposit / mortgage | `Global Assumptions!C82:C84` | 20% / 10.5% / 20 years |
| Other purchase costs | `Global Assumptions!C85` | 1.5% |
| New-home owner costs | `Global Assumptions!C86` | 2% of value annually |
| New-home growth | `Global Assumptions!C87` | 9.5% |
| Affordability threshold | `Global Assumptions!C88` | 35% |

## Fixed model decisions

Positive owner cash order across every housing and tax strategy:

1. Optimizer-selected RA contribution.
2. Pay tax, living, housing, and property-purchase requirements.
3. Max Matt and partner TFSAs separately.
4. Max Matt and partner GoalSaves separately.
5. Invest remainder in separate 12% taxable portfolios.

Deficit/purchase withdrawal order: deliberate cash, GoalSave, taxable portfolio after CGT, then TFSA. RA stays locked. Partner assets participate only when partner-funds toggle permits. Same-year deficits resolve before contributions, preventing contribution/withdrawal loops.

Opening Stay wealth is R2.6m: Disa R1.6m plus partner R1m allocated to partner TFSA R46k, GoalSave R250k, and taxable R704k. Immediate-sale opening wealth is R2.48m after R120k selling costs; R1.48m proceeds allocate to Matt TFSA R46k, GoalSave R250k, and taxable R1.184m.

Property terminal values use realizable equity after selling costs and modeled CGT. Disa future primary-residence qualification is 100% only for Stay; zero for other decisions. Company terminal value is 3x final annual operating profit plus retained assets without double counting, followed by modeled share-sale tax.

Tax Optimizer scores 216 fixed whole-horizon policies: six decisions × four salary policies × three dividend policies × three RA policies. Never optimize each year independently. Annual Model selected-policy result must reconcile to Tax Optimizer.

## Workbook map

- `Dashboard`: live ranking, asset decomposition, taxes, lifestyle cost, affordability, strategy.
- `Global Assumptions`: common editable defaults; hardcodes in column C.
- `Decision Assumptions`: scenario overrides C:H; effective inherited values J:O.
- `Revenue Path`: years 0–40. Global override B, then scenario override/effective pairs D:E, F:G, H:I, J:K, L:M, N:O.
- `Tax Optimizer`: winner per housing decision and reconciliation.
- `Annual Model`: exact selected-policy year 0–40 states.
- `Buy Matrix`: years 2–6 × R6m–R10m purchase cases.
- `Sensitivity`: major return/growth sensitivities.
- `Sources & Notes`: assumptions, definitions, limitations, URLs.
- `Strategy Engine`: hidden 216-strategy engine; do not hand-edit outputs.

Dashboard core outputs: feasibility B7:B12, rank C7:C12, real wealth D7:D12, nominal wealth E7:E12, liquid wealth F7:F12, asset buckets G:M, taxes N, lifestyle premium O, affordability P, strategy Q.

## Revenue overrides

Revenue Path row equals model year plus 5. Example: year 3 is row 8. Entering a value in blue override cell resets monthly revenue for that year; following years compound from reset using effective scenario growth. Use column B for all scenarios or scenario column D/F/H/J/L/N for one decision.

## Known limitations requiring disclosure

1. GoalSave workbook logic treats R250k as contributed capital and lets interest grow balance beyond R250k. Current GoTyme terms describe an aggregate balance cap. Never call multi-million GoalSave balances realistic; model corrected overflow destination explicitly before relying on bucket totals.
2. Tax-band/cap growth of 6% also inflates TFSA limits. Current R46k annual and R500k lifetime limits are statutory values, not guaranteed to grow. Flag this when TFSA results matter.
3. Sustained 12% portfolio and 9.5% property returns remain optimistic. Run lower cases before advice.
4. Partner opening taxable balance earns same 12% despite prior preference for safer 6.5% cash. Separate partner return when behavior differs.
5. Rental maintenance tied to property value can grow faster than rent and distort Keep/Rent result. Replace with actual levy, maintenance, insurance, agent, vacancy, and special-levy data when available.
6. Buying outcomes may show large terminal property equity while failing liquidity or affordability. Feasible flag controls recommendation.
7. Future tax and bank rates require current official verification. Never silently treat a current product rate as fixed for 40 years.

## Verification checklist

- Opening Stay wealth R2.6m; immediate sale wealth R2.48m.
- Year 1 business bridge equals revenue less operating costs before owner compensation.
- Revenue override resets requested year and compounds thereafter.
- Positive residual equals TFSA + GoalSave + taxable contributions.
- Deficits follow withdrawal waterfall; RA never funds housing.
- Separate TFSA limits, cost bases, CGT, donation toggle, and partner-funds toggle work.
- Property transition occurs once; mortgage reaches zero after term.
- Optimizer winner equals Annual Model terminal result, taxes, balances, and feasibility.
- `witan xlsx calc` returns zero errors.
- Every lint item is explained or fixed.
- Dashboard, changed assumption sheet, Tax Optimizer, Annual Model, and Buy Matrix render cleanly after structural edits.
