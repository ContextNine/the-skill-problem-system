const num = '"R" #,##0;[Red]("R" #,##0);-'
const pct = '0.0%'

function colLetter(n) {
  let s = ''
  while (n > 0) {
    const r = (n - 1) % 26
    s = String.fromCharCode(65 + r) + s
    n = Math.floor((n - 1) / 26)
  }
  return s
}

function dateFormula(iso) {
  const [y, m, d] = iso.split('-').map(Number)
  return `=DATE(${y},${m},${d})`
}

function monthLabel(iso) {
  const [y, m] = iso.split('-').map(Number)
  const names = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
  return `${names[m - 1]}-${String(y).slice(-2)}`
}

function cellValue(cell) {
  return cell && cell.value !== undefined && cell.value !== null ? cell.value : ''
}

async function existingRecords(name) {
  const meta = await xlsx.getListObject(wb, name)
  if (!meta.dataRange) return { meta, rows: [] }
  const cells = await xlsx.readRange(wb, meta.dataRange)
  const names = meta.columns.map(c => c.name)
  const rows = cells.map(row => {
    const record = {}
    names.forEach((name, idx) => {
      record[name] = cellValue(row[idx])
      record[`${name}__text`] = row[idx] ? row[idx].text : ''
    })
    return record
  })
  return { meta, rows }
}

function recordKey(row, flowName) {
  const month = row.Month__text || (typeof row.Month === 'string' ? monthLabel(row.Month) : String(row.Month || ''))
  return `${month}|${row[flowName] || ''}|${row.Category || ''}`
}

async function extendTimeline(targetMonths) {
  const bfSheets = await xlsx.listSheets(wb)
  const bf = bfSheets.find(s => s.sheet === 'Business Forecast')
  let currentMonths = Math.max(0, bf.cols - 1)
  if (targetMonths <= currentMonths) return
  const add = targetMonths - currentMonths
  let lastCol = currentMonths + 1
  await xlsx.insertColumnAfter(wb, 'Business Forecast', lastCol, add)
  for (let i = 0; i < add; i++) {
    const fromCol = colLetter(lastCol + i)
    const toCol = colLetter(lastCol + i + 1)
    await xlsx.copyRange(wb, `'Business Forecast'!${fromCol}5:${fromCol}42`, `'Business Forecast'!${toCol}5`, { pasteType: 'all' })
    await xlsx.setCells(wb, [{ address: `'Business Forecast'!${toCol}5`, formula: `=EDATE(${fromCol}5,1)`, format: 'mmm-yy' }])
  }

  const timelineSheets = [
    { sheet: 'Personal Monthly', fromCol: 'N', toCol: 'W', startRow: 6 },
    { sheet: 'Dashboard', fromCol: 'A', toCol: 'I', startRow: 21 },
    { sheet: 'Assets & Net Worth', fromCol: 'J', toCol: 'N', startRow: 6 },
  ]
  for (const spec of timelineSheets) {
    const lastRow = spec.startRow + currentMonths - 1
    await xlsx.insertRowAfter(wb, spec.sheet, lastRow, add)
    for (let i = 0; i < add; i++) {
      const fromRow = lastRow + i
      const toRow = fromRow + 1
      await xlsx.copyRange(wb, `'${spec.sheet}'!${spec.fromCol}${fromRow}:${spec.toCol}${fromRow}`, `'${spec.sheet}'!${spec.fromCol}${toRow}`, { pasteType: 'all' })
    }
  }
}

if (input.phase === 'preservation_export') {
  const business = await existingRecords('tblBusinessActuals')
  const personal = await existingRecords('tblPersonalMonthly')
  return {
    phase: input.phase,
    business: business.rows.filter(row => row.Month && row['Flow Type'] && row.Category).map(row => ({ key: recordKey(row, 'Flow Type'), row })),
    personal: personal.rows.filter(row => row.Month && row.Type && row.Category).map(row => ({ key: recordKey(row, 'Type'), row })),
  }
}

if (input.phase === 'setup_controls') {
const result = await xlsx.setCells(wb, [
  { address: "'Setup & Checks'!A4", value: 'Model start month' },
  { address: "'Setup & Checks'!B4", formula: dateFormula(input.model_start), format: 'mmm-yy', note: { text: `Source: statement pipeline cutoff ${input.cutoff_date}` } },
  { address: "'Setup & Checks'!A5", value: 'Business actual through' },
  { address: "'Setup & Checks'!B5", formula: dateFormula(input.business_actual_through), format: 'mmm-yy', note: { text: 'Source: latest validated business CSV transaction month' } },
  { address: "'Setup & Checks'!A6", value: 'Business opening cash' },
  { address: "'Setup & Checks'!B6", value: input.business_opening_cash, format: num, note: { text: `Source: balance immediately before ${input.cutoff_date}` } },
  { address: "'Setup & Checks'!A7", value: 'Personal opening cash' },
  { address: "'Setup & Checks'!B7", value: input.personal_opening_cash, format: num, note: { text: `Source: balance immediately before ${input.cutoff_date}` } },
  { address: "'Setup & Checks'!A11", value: 'Future forecast months' },
  { address: "'Setup & Checks'!B11", value: input.future_forecast_months },
  { address: "'Setup & Checks'!A17", value: 'Personal actual through' },
  { address: "'Setup & Checks'!B17", formula: dateFormula(input.personal_actual_through), format: 'mmm-yy', note: { text: 'Source: latest validated personal CSV transaction month' } },
  { address: "'Setup & Checks'!A18", value: 'Personal variable expense baseline' },
  { address: "'Setup & Checks'!B18", value: input.personal_variable_baseline, format: num, note: { text: 'Source: trailing six-month average of non-recurring personal actuals' } },
  { address: "'Setup & Checks'!C19", value: 'Business variable expense baseline' },
  { address: "'Setup & Checks'!D19", value: input.business_expense_baseline, format: num, note: { text: 'Source: trailing six-month average of non-recurring business expenses' } },
  { address: "'Setup & Checks'!C20", value: 'Business variable receipt baseline' },
  { address: "'Setup & Checks'!D20", value: input.business_receipt_baseline, format: num, note: { text: 'Source: trailing six-month average of non-recurring business receipts' } },
  { address: "'Setup & Checks'!A27", value: 'Owner pay method' },
  { address: "'Setup & Checks'!B27", value: input.owner_pay_method || 'Ad hoc draw', note: { text: 'Ad hoc draws are entered by month in tblBizForecastInputs' } },
  { address: "'Setup & Checks'!A28", value: 'Owner pay mechanism conflict' },
  { address: "'Setup & Checks'!B28", formula: '=IF(AND(B27="Ad hoc draw",COUNTIFS(tblRecurring[Entity],"Business",tblRecurring[Flow Type],"Owner Pay",tblRecurring[Active],"Yes")>0),"CHECK","OK")' },
  { address: "'Setup & Checks'!A29", value: 'Business receipt KPI reconciliation' },
  { address: "'Setup & Checks'!B29", formula: '=IF(ABS(SUM(\'Business Forecast\'!B12:AK12)-SUM(\'Business Forecast\'!B8:AK8)-SUM(\'Business Forecast\'!B9:AK9)-SUM(\'Business Forecast\'!B10:AK10)-SUM(\'Business Forecast\'!B11:AK11)-SUMPRODUCT(--(\'Business Forecast\'!B5:AK5>$B$5))*$D$20)<0.01,"OK","CHECK")' },
  { address: "'Setup & Checks'!B26", formula: '=IF(AND(B21="OK",B22="OK",B23="OK",B24="OK",B25="OK",B28="OK",B29="OK"),"OK","CHECK")' },
])
return { phase: input.phase, errors: result.errors }
}

if (input.phase === 'recurring_setup') {
  const existing = await existingRecords('tblRecurring')
  const reviewedItems = new Set(input.commitments.map(row => `${row.entity}|${row.item}`))
  const rows = input.commitments.map(row => [
    { value: row.entity }, { value: row.flow_type }, { value: row.item }, { value: row.category },
    row.amount === '' ? {} : { value: Number(row.amount), format: num }, { value: row.frequency || 'Monthly' },
    row.start_month ? { formula: dateFormula(row.start_month), format: 'mmm-yy' } : { value: 0, format: ';;;' },
    row.end_month ? { formula: dateFormula(row.end_month), format: 'mmm-yy' } : {},
    { value: Number(row.annual_escalation || 0), format: pct }, { value: row.active || 'No' },
    {},
    { value: row.notes || '' },
  ])
  for (const row of existing.rows) {
    if (!row.Item || reviewedItems.has(`${row.Entity}|${row.Item}`)) continue
    rows.push([
      { value: row.Entity || '' }, { value: row['Flow Type'] || '' }, { value: row.Item }, { value: row.Category || '' },
      {}, { value: 'Monthly' },
      { value: 0, format: ';;;' }, {},
      { value: 0, format: pct }, { value: 'No' },
      {},
      { value: String(row.Notes || '').includes('Needs confirmation') ? row.Notes : `${row.Notes ? `${row.Notes}; ` : ''}Needs confirmation` },
    ])
  }
  await xlsx.setListObject(wb, 'tblRecurring', {
    ref: `A5:L${5 + Math.max(1, rows.length)}`,
    columns: [
      { name: 'Entity' }, { name: 'Flow Type' }, { name: 'Item' }, { name: 'Category' },
      { name: 'Amount' }, { name: 'Frequency' }, { name: 'Start Month' }, { name: 'End Month' },
      { name: 'Annual Escalation %' }, { name: 'Active' },
      { name: 'Monthly Amount', calculatedColumnFormula: '=IF(E6="",0,IF(F6="Monthly",N(E6),IF(F6="Quarterly",N(E6)/3,IF(F6="Annual",N(E6)/12,IF(F6="Weekly",N(E6)*52/12,N(E6))))))' },
      { name: 'Notes' },
    ],
    rows,
  })
  return { phase: input.phase, recurringRows: rows.length, activeRows: input.commitments.filter(row => row.active === 'Yes').length }
}

if (input.phase === 'kpi_split') {
  const endRow = 20 + input.timeline_months
  const cells = [
    { address: `'Business Forecast'!A20`, value: 'Owner pay / draw' },
    { address: 'Dashboard!A5', value: 'Customer revenue' },
    { address: 'Dashboard!B5', formula: '=IFERROR(INDEX(\'Business Forecast\'!$B$8:$AK$8,1,MATCH($E$3,\'Business Forecast\'!$B$5:$AK$5,0)),0)', format: num },
    { address: 'Dashboard!D5', value: 'Owner funding' },
    { address: 'Dashboard!E5', formula: '=IFERROR(INDEX(\'Business Forecast\'!$B$10:$AK$10,1,MATCH($E$3,\'Business Forecast\'!$B$5:$AK$5,0)),0)', format: num },
    { address: 'Dashboard!G5', value: 'Core operating expenses' },
    { address: 'Dashboard!H5', formula: '=IFERROR(INDEX(\'Business Forecast\'!$B$29:$AK$29,1,MATCH($E$3,\'Business Forecast\'!$B$5:$AK$5,0))-INDEX(\'Business Forecast\'!$B$20:$AK$20,1,MATCH($E$3,\'Business Forecast\'!$B$5:$AK$5,0)),0)', format: num },
    { address: 'Dashboard!J5', value: 'Closing business cash' },
    { address: 'Dashboard!K5', formula: '=IFERROR(INDEX(\'Business Forecast\'!$B$40:$AK$40,1,MATCH($E$3,\'Business Forecast\'!$B$5:$AK$5,0)),0)', format: num },
    { address: 'Dashboard!A7', value: 'Business net cash flow' },
    { address: 'Dashboard!B7', formula: '=IFERROR(INDEX(\'Business Forecast\'!$B$38:$AK$38,1,MATCH($E$3,\'Business Forecast\'!$B$5:$AK$5,0)),0)', format: num },
    { address: 'Dashboard!D7', value: 'Business runway' },
    { address: 'Dashboard!E7', formula: '=IFERROR(INDEX(\'Business Forecast\'!$B$42:$AK$42,1,MATCH($E$3,\'Business Forecast\'!$B$5:$AK$5,0)),0)', format: '0.0' },
    { address: 'Dashboard!G7', value: 'Business recurring / month' },
    { address: 'Dashboard!H7', formula: '=SUMPRODUCT((tblRecurring[Entity]="Business")*(tblRecurring[Flow Type]="Operating Expense")*(tblRecurring[Active]="Yes")*(tblRecurring[Start Month]<=$E$3)*((tblRecurring[End Month]="")+(tblRecurring[End Month]>=$E$3))*tblRecurring[Monthly Amount]*(1+tblRecurring[Annual Escalation %])^INT(((YEAR($E$3)-YEAR(tblRecurring[Start Month]))*12+MONTH($E$3)-MONTH(tblRecurring[Start Month]))/12))', format: num },
    { address: 'Dashboard!A13', value: 'Core operating expenses — FY' },
    { address: 'Dashboard!B13', formula: '=SUMIFS(\'Business Forecast\'!$B$29:$AK$29,\'Business Forecast\'!$B$5:$AK$5,">="&DATE($B$3-1,3,1),\'Business Forecast\'!$B$5:$AK$5,"<="&DATE($B$3,2,1))-SUMIFS(\'Business Forecast\'!$B$20:$AK$20,\'Business Forecast\'!$B$5:$AK$5,">="&DATE($B$3-1,3,1),\'Business Forecast\'!$B$5:$AK$5,"<="&DATE($B$3,2,1))', format: num },
    { address: 'Dashboard!A20', value: 'Month' }, { address: 'Dashboard!B20', value: 'Customer revenue' },
    { address: 'Dashboard!C20', value: 'Owner funding' }, { address: 'Dashboard!D20', value: 'Core operating expenses' },
    { address: 'Dashboard!E20', value: 'Closing cash' },
  ]
  const ownerPayCategory = '"Salary / owner pay"'
  for (let row = 21; row <= endRow; row++) {
    const sourceCol = colLetter(row - 19)
    cells.push({ address: `'Business Forecast'!${sourceCol}20`, formula: `=IF(${sourceCol}$5<='Setup & Checks'!$B$5,SUMIFS(tblBusinessActuals[Amount],tblBusinessActuals[Month],${sourceCol}$5,tblBusinessActuals[Flow Type],"Owner Pay",tblBusinessActuals[Category],${ownerPayCategory}),IF(COUNTIFS(tblBizForecastInputs[Month],${sourceCol}$5,tblBizForecastInputs[Category],${ownerPayCategory},tblBizForecastInputs[Scenario],'Setup & Checks'!$B$8,tblBizForecastInputs[Input Type],"Override")>0,SUMIFS(tblBizForecastInputs[Amount],tblBizForecastInputs[Month],${sourceCol}$5,tblBizForecastInputs[Category],${ownerPayCategory},tblBizForecastInputs[Scenario],'Setup & Checks'!$B$8,tblBizForecastInputs[Input Type],"Override"),IF(COUNTIFS(tblBizForecastInputs[Month],${sourceCol}$5,tblBizForecastInputs[Category],${ownerPayCategory},tblBizForecastInputs[Scenario],"All",tblBizForecastInputs[Input Type],"Override")>0,SUMIFS(tblBizForecastInputs[Amount],tblBizForecastInputs[Month],${sourceCol}$5,tblBizForecastInputs[Category],${ownerPayCategory},tblBizForecastInputs[Scenario],"All",tblBizForecastInputs[Input Type],"Override"),(SUMPRODUCT((tblRecurring[Entity]="Business")*(tblRecurring[Flow Type]="Owner Pay")*(tblRecurring[Category]=${ownerPayCategory})*(tblRecurring[Active]="Yes")*(tblRecurring[Start Month]<=${sourceCol}$5)*((tblRecurring[End Month]="")+(tblRecurring[End Month]>=${sourceCol}$5))*tblRecurring[Monthly Amount]*(1+tblRecurring[Annual Escalation %])^INT(((YEAR(${sourceCol}$5)-YEAR(tblRecurring[Start Month]))*12+MONTH(${sourceCol}$5)-MONTH(tblRecurring[Start Month]))/12))*--('Setup & Checks'!$B$27<>"Ad hoc draw")+SUMIFS(tblBizForecastInputs[Amount],tblBizForecastInputs[Month],${sourceCol}$5,tblBizForecastInputs[Category],${ownerPayCategory},tblBizForecastInputs[Scenario],'Setup & Checks'!$B$8,tblBizForecastInputs[Input Type],"Additive")+SUMIFS(tblBizForecastInputs[Amount],tblBizForecastInputs[Month],${sourceCol}$5,tblBizForecastInputs[Category],${ownerPayCategory},tblBizForecastInputs[Scenario],"All",tblBizForecastInputs[Input Type],"Additive"))*(1+'Setup & Checks'!$B$16))))`, format: num })
    cells.push({ address: `Dashboard!A${row}`, formula: `='Business Forecast'!${sourceCol}5`, format: 'mmm-yy' })
    cells.push({ address: `Dashboard!B${row}`, formula: `='Business Forecast'!${sourceCol}8`, format: num })
    cells.push({ address: `Dashboard!C${row}`, formula: `='Business Forecast'!${sourceCol}10`, format: num })
    cells.push({ address: `Dashboard!D${row}`, formula: `='Business Forecast'!${sourceCol}29-'Business Forecast'!${sourceCol}20`, format: num })
    cells.push({ address: `Dashboard!E${row}`, formula: `='Business Forecast'!${sourceCol}40`, format: num })
  }
  await xlsx.setCells(wb, cells)
  const chart = await xlsx.getChart(wb, 'Dashboard', 'BusinessTrend')
  chart.title = { text: 'Business revenue, owner funding, core costs and cash' }
  chart.groups = [
    { type: 'line', axis: 'secondary', series: [{ name: { ref: 'Dashboard!E20' }, categories: `Dashboard!A21:A${endRow}`, categoriesRefType: 'number', values: `Dashboard!E21:E${endRow}`, lineColor: '#4472C4', lineWidth: 2, marker: { style: 'none' } }] },
    { type: 'column', axis: 'primary', grouping: 'standard', gapWidth: 120, series: [
      { name: { ref: 'Dashboard!B20' }, categories: `Dashboard!A21:A${endRow}`, categoriesRefType: 'number', values: `Dashboard!B21:B${endRow}`, fillColor: '#70AD47' },
      { name: { ref: 'Dashboard!C20' }, categories: `Dashboard!A21:A${endRow}`, categoriesRefType: 'number', values: `Dashboard!C21:C${endRow}`, fillColor: '#5B9BD5' },
      { name: { ref: 'Dashboard!D20' }, categories: `Dashboard!A21:A${endRow}`, categoriesRefType: 'number', values: `Dashboard!D21:D${endRow}`, fillColor: '#ED7D31' },
    ] },
  ]
  await xlsx.setChart(wb, 'Dashboard', 'BusinessTrend', chart)
  const personalChart = await xlsx.getChart(wb, 'Dashboard', 'PersonalTrend')
  await xlsx.setChart(wb, 'Dashboard', 'PersonalTrend', personalChart)
  return { phase: input.phase, endRow }
}

if (input.phase === 'setup_personal_timeline') {
const cells = []
for (let row = input.start_row; row < input.start_row + input.row_count; row++) {
  cells.push({ address: `'Personal Monthly'!P${row}`, formula: `=SUMIFS(tblRecurring[Monthly Amount],tblRecurring[Entity],"Personal",tblRecurring[Flow Type],"Income",tblRecurring[Active],"Yes",tblRecurring[Start Month],"<="&N${row},tblRecurring[End Month],">="&N${row})+SUMIFS(tblRecurring[Monthly Amount],tblRecurring[Entity],"Personal",tblRecurring[Flow Type],"Income",tblRecurring[Active],"Yes",tblRecurring[Start Month],"<="&N${row},tblRecurring[End Month],"")+SUMIFS(tblPersonalMonthly[Budget Adjustment],tblPersonalMonthly[Month],N${row},tblPersonalMonthly[Type],"Income")`, format: num })
  cells.push({ address: `'Personal Monthly'!Q${row}`, formula: `=SUMIFS(tblPersonalMonthly[Actual],tblPersonalMonthly[Month],N${row},tblPersonalMonthly[Type],"Income")`, format: num })
  cells.push({ address: `'Personal Monthly'!R${row}`, formula: `=SUMIFS(tblRecurring[Monthly Amount],tblRecurring[Entity],"Personal",tblRecurring[Flow Type],"Expense",tblRecurring[Active],"Yes",tblRecurring[Start Month],"<="&N${row},tblRecurring[End Month],">="&N${row})+SUMIFS(tblRecurring[Monthly Amount],tblRecurring[Entity],"Personal",tblRecurring[Flow Type],"Expense",tblRecurring[Active],"Yes",tblRecurring[Start Month],"<="&N${row},tblRecurring[End Month],"")+SUMIFS(tblPersonalMonthly[Budget Adjustment],tblPersonalMonthly[Month],N${row},tblPersonalMonthly[Type],"Expense")+'Setup & Checks'!$B$18`, format: num })
  cells.push({ address: `'Personal Monthly'!S${row}`, formula: `=SUMIFS(tblPersonalMonthly[Actual],tblPersonalMonthly[Month],N${row},tblPersonalMonthly[Type],"Expense")`, format: num })
  cells.push({ address: `'Personal Monthly'!U${row}`, formula: `=IF(N${row}<='Setup & Checks'!$B$17,O${row}+Q${row}-S${row},T${row})`, format: num })
  cells.push({ address: `'Personal Monthly'!W${row}`, formula: `=IF(N${row}<='Setup & Checks'!$B$17,S${row},R${row})`, format: num })
}
const result = await xlsx.setCells(wb, cells)
return { phase: input.phase, cells: cells.length, errors: result.errors }
}

if (input.phase === 'setup_business_baseline') {
const cells = []
for (let col = input.start_col; col < input.start_col + input.col_count; col++) {
  const letter = colLetter(col)
  cells.push({ address: `'Business Forecast'!${letter}12`, formula: `=SUM(${letter}8:${letter}11)+IF(${letter}$5>'Setup & Checks'!$B$5,'Setup & Checks'!$D$20,0)`, format: num })
  cells.push({ address: `'Business Forecast'!${letter}29`, formula: `=SUM(${letter}15:${letter}28)+IF(${letter}$5>'Setup & Checks'!$B$5,'Setup & Checks'!$D$19,0)`, format: num })
}
const result = await xlsx.setCells(wb, cells)
return { phase: input.phase, cells: cells.length, errors: result.errors }
}

if (input.phase === 'model_suspend') {
await xlsx.setCells(wb, [{ address: `'Setup & Checks'!B5`, formula: '=DATE(2099,12,1)', format: 'mmm-yy' }])
return { phase: input.phase }
}

if (input.phase === 'model_restore') {
return { phase: input.phase, restoredBy: 'setup-controls-and-timeline-phases' }
}

if (input.phase === 'business_init') {
await xlsx.setListObject(wb, 'tblBusinessActuals', {
  ref: `A5:M${5 + Math.max(1, input.row_count)}`,
  columns: [
    { name: 'Month' }, { name: 'Tax Year' }, { name: 'Flow Type' }, { name: 'Category' },
    { name: 'Amount' }, { name: 'Recurring Amount' }, { name: 'Variable Amount' },
    { name: 'Verified' }, { name: 'Notes' }, { name: 'Source' },
    { name: 'Trailing 6M Average' }, { name: 'Variance %' }, { name: 'Anomaly' },
  ],
})
return { phase: input.phase, rowCount: input.row_count }
}

if (input.phase === 'business_chunk') {
const cells = []
input.rows.forEach((row, rowOffset) => row.forEach((value, colOffset) => cells.push({
  address: `'Business Actuals'!${colLetter(colOffset + 1)}${input.start_row + rowOffset}`,
  value,
})))
await xlsx.setCells(wb, cells)
return { phase: input.phase, startRow: input.start_row, rows: input.rows.length }
}

if (input.phase === 'business_actuals') {
const businessExisting = await existingRecords('tblBusinessActuals')
const businessPipelineKeys = input.business_rows.map(r => `${monthLabel(r[0])}|${r[2]}|${r[3]}`)
const businessRows = input.business_rows.map(r => {
  const wanted = `${monthLabel(r[0])}|${r[2]}|${r[3]}`
  const old = businessExisting.rows.find(row => recordKey(row, 'Flow Type') === wanted) || {}
  return [
    { formula: dateFormula(r[0]), format: 'mmm-yy' }, { value: Number(r[1]) },
    { value: r[2] }, { value: r[3] }, { value: Number(r[4]), format: num },
    { value: Number(r[5]), format: num }, { value: Number(r[6]), format: num },
    { value: 'Yes' }, { value: old.Notes || '' }, { value: input.source_tag },
    { value: r[7] === '' ? '' : Number(r[7]), format: num },
    { value: r[8] === '' ? '' : Number(r[8]), format: pct }, { value: r[9] || '' },
  ]
})
for (const row of businessExisting.rows) {
  const key = recordKey(row, 'Flow Type')
  const source = row.Source || ''
  if (row.Month && row['Flow Type'] && row.Category && !businessPipelineKeys.includes(key) && !String(source).startsWith('pipeline:')) {
    businessRows.push([
      { value: row.Month, format: 'mmm-yy' }, {}, { value: row['Flow Type'] }, { value: row.Category },
      { value: Number(row.Amount || 0), format: num }, { value: Number(row['Recurring Amount'] || 0), format: num },
      { value: Number(row['Variable Amount'] || row.Amount || 0), format: num }, { value: row.Verified || 'No' },
      { value: row.Notes || '' }, { value: source }, {}, {}, {},
    ])
  }
}
const businessEndRow = 5 + Math.max(1, businessRows.length)
await xlsx.setListObject(wb, 'tblBusinessActuals', {
  ref: `A5:M${businessEndRow}`,
  columns: [
    { name: 'Month' },
    { name: 'Tax Year' },
    { name: 'Flow Type' }, { name: 'Category' }, { name: 'Amount' },
    { name: 'Recurring Amount' }, { name: 'Variable Amount' }, { name: 'Verified' },
    { name: 'Notes' }, { name: 'Source' },
    { name: 'Trailing 6M Average' }, { name: 'Variance %' }, { name: 'Anomaly' },
  ],
  rows: businessRows,
})
return { phase: input.phase, businessRows: businessRows.length }
}

if (input.phase === 'personal_init') {
const sheets = await xlsx.listSheets(wb)
if (!sheets.some(s => s.sheet === 'Personal Actuals')) {
  await xlsx.renameSheet(wb, 'Personal Monthly', 'Personal Actuals')
  await xlsx.addSheet(wb, 'Personal Monthly')
  await xlsx.copyRange(wb, `'Personal Actuals'!N1:W41`, `'Personal Monthly'!N1`, { pasteType: 'all' })
  for (const sheet of ['Dashboard', 'Setup & Checks']) {
    await xlsx.findAndReplace(wb, "'Personal Actuals'!", "'Personal Monthly'!", {
      in: { sheet }, inFormulas: true, limit: 5000,
    })
  }
}
await xlsx.setListObject(wb, 'tblPersonalMonthly', {
  ref: `A5:H${5 + Math.max(1, input.row_count)}`,
  columns: [
    { name: 'Month' }, { name: 'Type' }, { name: 'Category' }, { name: 'Budget Adjustment' },
    { name: 'Actual' }, { name: 'Recurring Actual' }, { name: 'Variable Actual' }, { name: 'Notes' },
  ],
})
return { phase: input.phase, rowCount: input.row_count, sheet: 'Personal Actuals', mode: 'renamed-sheet' }
}

if (input.phase === 'personal_finalize') {
const meta = await xlsx.getListObject(wb, 'tblPersonalMonthly')
return { phase: input.phase, rowCount: input.row_count, ref: meta.ref }
}

if (input.phase === 'personal_chunk') {
const cells = []
input.rows.forEach((row, rowOffset) => row.forEach((value, colOffset) => cells.push({
  address: `'Personal Actuals'!${colLetter(colOffset + 1)}${input.start_row + rowOffset}`,
  value,
})))
await xlsx.setCells(wb, cells)
return { phase: input.phase, startRow: input.start_row, rows: input.rows.length }
}

if (input.phase === 'forecast_init') {
await xlsx.setListObject(wb, 'tblBizForecastInputs', {
  ref: `A50:F${50 + Math.max(1, input.row_count)}`,
  columns: [{ name: 'Month' }, { name: 'Category' }, { name: 'Scenario' }, { name: 'Input Type' }, { name: 'Amount' }, { name: 'Notes' }],
})
return { phase: input.phase, rowCount: input.row_count }
}

if (input.phase === 'forecast_suspend') {
await xlsx.setCells(wb, [{ address: `'Setup & Checks'!B5`, formula: '=DATE(2099,12,1)', format: 'mmm-yy' }])
return { phase: input.phase }
}

if (input.phase === 'forecast_chunk') {
const cells = []
input.rows.forEach((row, rowOffset) => row.forEach((value, colOffset) => cells.push({
  address: `'Business Forecast'!${colLetter(colOffset + 1)}${input.start_row + rowOffset}`,
  value,
})))
await xlsx.setCells(wb, cells)
return { phase: input.phase, startRow: input.start_row, rows: input.rows.length }
}

if (input.phase === 'business_forecast') {
const forecastExisting = await existingRecords('tblBizForecastInputs')
const manualForecastRows = forecastExisting.rows.filter(row => row.Month && row.Category && !String(row.Notes || '').startsWith('pipeline-variable-baseline'))
const forecastRows = manualForecastRows.map(row => [
  { value: row.Month, format: 'mmm-yy' }, { value: row.Category }, { value: row.Scenario },
  { value: row['Input Type'] }, { value: Number(row.Amount || 0), format: num }, { value: row.Notes || '' },
])
for (const r of input.business_forecast_inputs) {
  forecastRows.push([
    { formula: dateFormula(r[0]), format: 'mmm-yy' }, { value: r[1] }, { value: r[2] },
    { value: r[3] }, { value: Number(r[4]), format: num },
    { value: `pipeline-variable-baseline:${input.source_tag}` },
  ])
}
const forecastEndRow = 50 + Math.max(1, forecastRows.length)
await xlsx.setListObject(wb, 'tblBizForecastInputs', {
  ref: `A50:F${forecastEndRow}`,
  columns: [{ name: 'Month' }, { name: 'Category' }, { name: 'Scenario' }, { name: 'Input Type' }, { name: 'Amount' }, { name: 'Notes' }],
  rows: forecastRows,
})
return { phase: input.phase, forecastRows: forecastRows.length }
}

if (input.phase === 'net_worth') {
const netWorthExisting = await existingRecords('tblNetWorthSnapshots')
const manualNetWorth = netWorthExisting.rows.filter(row => row.Month && row.Item && !String(row.Notes || '').startsWith('pipeline-personal-cash'))
const netWorthRows = manualNetWorth.map(row => [
  { value: row.Month, format: 'mmm-yy' }, { value: row.Item }, { value: row['Position Type'] },
  { value: Number(row.Value || 0), format: num }, { value: row['Include in Net Worth'] || 'Yes' }, { value: row.Notes || '' },
])
for (const r of input.personal_cash_rows) {
  netWorthRows.push([
    { formula: dateFormula(r[0]), format: 'mmm-yy' }, { value: r[1] }, { value: r[2] },
    { value: Number(r[3]), format: num }, { value: r[4] },
    { value: `pipeline-personal-cash:${input.source_tag}` },
  ])
}
const netWorthEndRow = 17 + Math.max(1, netWorthRows.length)
await xlsx.setListObject(wb, 'tblNetWorthSnapshots', {
  ref: `A17:F${netWorthEndRow}`,
  columns: [{ name: 'Month' }, { name: 'Item' }, { name: 'Position Type' }, { name: 'Value' }, { name: 'Include in Net Worth' }, { name: 'Notes' }],
  rows: netWorthRows,
})
return { phase: input.phase, netWorthRows: netWorthRows.length }
}

if (input.phase === 'finish_categories') {
  const aliases = ['Salary / wages', 'Other income', 'Rent / mortgage', 'Health insurance', 'WiFi & internet',
    'Subscriptions & software', 'Bank fees', 'Gym', 'Insurance', 'Medical & dental', 'Food & groceries',
    'Toiletries & cleaning', 'Fuel & transport', 'Recreation', 'Car maintenance', 'Laundry', 'Phone',
    'Electricity', 'Tax', 'Other expenses']
  const combined = [...input.business_categories, ...input.personal_categories, ...aliases].filter((value, idx, all) => all.indexOf(value) === idx)
  await xlsx.setCells(wb, [
    { address: `'Pipeline Lists'!A1`, value: 'Personal Categories' },
    { address: `'Pipeline Lists'!B1`, value: 'Combined Categories' },
    { address: `'Pipeline Lists'!C1`, value: 'Owner Pay Methods' },
    { address: `'Pipeline Lists'!C2`, value: 'Salary' },
    { address: `'Pipeline Lists'!C3`, value: 'Fixed draw' },
    { address: `'Pipeline Lists'!C4`, value: 'Ad hoc draw' },
    ...input.personal_categories.map((value, idx) => ({ address: `'Pipeline Lists'!A${2 + idx}`, value })),
    ...combined.map((value, idx) => ({ address: `'Pipeline Lists'!B${2 + idx}`, value })),
  ])
  return { phase: input.phase, combinedCount: combined.length }
}

if (input.phase === 'finish_names') {
  const aliases = ['Salary / wages', 'Other income', 'Rent / mortgage', 'Health insurance', 'WiFi & internet',
    'Subscriptions & software', 'Bank fees', 'Gym', 'Insurance', 'Medical & dental', 'Food & groceries',
    'Toiletries & cleaning', 'Fuel & transport', 'Recreation', 'Car maintenance', 'Laundry', 'Phone',
    'Electricity', 'Tax', 'Other expenses']
  const combined = [...input.business_categories, ...input.personal_categories, ...aliases].filter((value, idx, all) => all.indexOf(value) === idx)
  for (const name of ['PersonalCategories', 'CombinedCategories', 'OwnerPayMethods']) {
    try { await xlsx.deleteDefinedName(wb, name) } catch (_) {}
  }
  await xlsx.addDefinedName(wb, 'PersonalCategories', `'Pipeline Lists'!$A$2:$A$${1 + input.personal_categories.length}`)
  await xlsx.addDefinedName(wb, 'CombinedCategories', `'Pipeline Lists'!$B$2:$B$${1 + combined.length}`)
  await xlsx.addDefinedName(wb, 'OwnerPayMethods', `'Pipeline Lists'!$C$2:$C$4`)
  return { phase: input.phase }
}

if (input.phase === 'finish_validations') {
  const businessMeta = await xlsx.getListObject(wb, 'tblBusinessActuals')
  const personalMeta = await xlsx.getListObject(wb, 'tblPersonalMonthly')
  const businessEndRow = Number((businessMeta.ref.match(/\d+$/) || ['6'])[0])
  const personalEndRow = Number((personalMeta.ref.match(/\d+$/) || ['6'])[0])
  await xlsx.removeDataValidations(wb, 'Business Actuals', { address: `F6:F${businessEndRow}` })
  await xlsx.setDataValidations(wb, 'Business Actuals', [
    { address: `C6:C${businessEndRow}`, rule: { list: { source: '=BusinessFlowTypes', inCellDropDown: true } }, ignoreBlanks: true },
    { address: `D6:D${businessEndRow}`, rule: { list: { source: '=BusinessCategories', inCellDropDown: true } }, ignoreBlanks: true },
    { address: `H6:H${businessEndRow}`, rule: { list: { source: '=YesNo', inCellDropDown: true } }, ignoreBlanks: true },
  ])
  await xlsx.setDataValidations(wb, 'Personal Actuals', [
    { address: `B6:B${personalEndRow}`, rule: { list: { source: '=PersonalTypes', inCellDropDown: true } }, ignoreBlanks: true },
    { address: `C6:C${personalEndRow}`, rule: { list: { source: '=PersonalCategories', inCellDropDown: true } }, ignoreBlanks: true },
  ])
  await xlsx.setDataValidations(wb, 'Setup & Checks', [
    { address: 'B27', rule: { list: { source: '=OwnerPayMethods', inCellDropDown: true } }, ignoreBlanks: false },
  ])
  return { phase: input.phase, businessEndRow, personalEndRow }
}

if (input.phase === 'finish_add_sheets') {
  const sheets = await xlsx.listSheets(wb)
  for (const name of ['Pipeline Lists', 'Import Status', 'Personal Forecast Baseline', 'Business Forecast Baseline']) {
    if (!sheets.some(s => s.sheet === name)) await xlsx.addSheet(wb, name)
  }
  return { phase: input.phase }
}

if (input.phase === 'finish_status_data') {
  const statusRows = [
    ['STATEMENT PIPELINE STATUS', ''], ['Pipeline version', input.pipeline_version],
    ['State hash', input.state_hash], ['Cutoff date', input.cutoff_date],
    ['Business actual through', input.business_actual_through], ['Personal actual through', input.personal_actual_through],
    ['Timeline end', input.timeline_end], ['Personal transactions', input.status.personal_transaction_rows],
    ['Business transactions', input.status.business_transaction_rows], ['Personal source CSVs', input.status.personal_source_files],
    ['Business source CSVs', input.status.business_source_files], ['Personal coverage', input.status.personal_coverage],
    ['Business coverage', input.status.business_coverage], ['Low-confidence classifications', input.status.low_confidence],
    ['Validation failures', input.status.validation_failures], ['Workbook source tag', input.source_tag],
    ['Last successful run', input.run_timestamp],
  ]
  await xlsx.setCells(wb, statusRows.flatMap((row, idx) => [
    { address: `Import Status!A${idx + 1}`, value: row[0] }, { address: `Import Status!B${idx + 1}`, value: row[1] },
  ]))
  return { phase: input.phase }
}

if (input.phase === 'finish_personal_baseline_data') {
  const cells = [
    { address: `'Personal Forecast Baseline'!A1`, value: 'PERSONAL VARIABLE EXPENSE BASELINE' },
    { address: `'Personal Forecast Baseline'!A2`, value: 'Category' },
    { address: `'Personal Forecast Baseline'!B2`, value: 'Trailing 6M average' },
  ]
  input.personal_baselines.forEach((row, idx) => {
    cells.push({ address: `'Personal Forecast Baseline'!A${idx + 3}`, value: row[0] })
    cells.push({ address: `'Personal Forecast Baseline'!B${idx + 3}`, value: Number(row[1]), format: num })
  })
  await xlsx.setCells(wb, cells)
  return { phase: input.phase, rows: input.personal_baselines.length }
}

if (input.phase === 'finish_business_baseline_data') {
  const cells = [
    { address: `'Business Forecast Baseline'!A1`, value: 'BUSINESS VARIABLE FORECAST BASELINE' },
    { address: `'Business Forecast Baseline'!A2`, value: 'Flow type' },
    { address: `'Business Forecast Baseline'!B2`, value: 'Category' },
    { address: `'Business Forecast Baseline'!C2`, value: 'Trailing 6M average' },
  ]
  input.business_baselines.forEach((row, idx) => {
    cells.push({ address: `'Business Forecast Baseline'!A${idx + 3}`, value: row[0] })
    cells.push({ address: `'Business Forecast Baseline'!B${idx + 3}`, value: row[1] })
    cells.push({ address: `'Business Forecast Baseline'!C${idx + 3}`, value: Number(row[2]), format: num })
  })
  await xlsx.setCells(wb, cells)
  return { phase: input.phase, rows: input.business_baselines.length }
}

if (input.phase === 'finish_status_style') {
  await xlsx.setStyle(wb, 'Import Status!A1:B1', { fill: { color: '#1F3864' }, font: { color: '#FFFFFF', bold: true } })
  await xlsx.setStyle(wb, 'Import Status!A2:A17', { font: { bold: true } })
  await xlsx.setSheetProperties(wb, 'Import Status', { view: { showGridLines: false } })
  await xlsx.autoFitColumns(wb, 'Import Status', ['A', 'B'], { minWidth: 12, maxWidth: 50, padding: 2 })
  return { phase: input.phase }
}

if (input.phase === 'finish_baseline_style') {
  for (const spec of [
    ['Personal Forecast Baseline', 'A1:B1', 'A2:B2', ['A', 'B']],
    ['Business Forecast Baseline', 'A1:C1', 'A2:C2', ['A', 'B', 'C']],
  ]) {
    await xlsx.setStyle(wb, `'${spec[0]}'!${spec[1]}`, { fill: { color: '#1F3864' }, font: { color: '#FFFFFF', bold: true } })
    await xlsx.setStyle(wb, `'${spec[0]}'!${spec[2]}`, { fill: { color: '#D9EAF7' }, font: { bold: true } })
    await xlsx.setSheetProperties(wb, spec[0], { view: { showGridLines: false } })
    await xlsx.autoFitColumns(wb, spec[0], spec[3], { minWidth: 14, maxWidth: 40, padding: 2 })
  }
  return { phase: input.phase }
}

if (input.phase === 'finish_model_style') {
  const businessMeta = await xlsx.getListObject(wb, 'tblBusinessActuals')
  const personalMeta = await xlsx.getListObject(wb, 'tblPersonalMonthly')
  const forecastMeta = await xlsx.getListObject(wb, 'tblBizForecastInputs')
  const netWorthMeta = await xlsx.getListObject(wb, 'tblNetWorthSnapshots')
  const businessEndRow = Number((businessMeta.ref.match(/\d+$/) || ['6'])[0])
  const personalEndRow = Number((personalMeta.ref.match(/\d+$/) || ['6'])[0])
  const forecastEndRow = Number((forecastMeta.ref.match(/\d+$/) || ['51'])[0])
  const netWorthEndRow = Number((netWorthMeta.ref.match(/\d+$/) || ['18'])[0])
  await xlsx.setStyle(wb, `Business Actuals!A6:A${businessEndRow}`, { numberFormat: 'mmm-yy' })
  await xlsx.setStyle(wb, `Business Actuals!E6:G${businessEndRow}`, { numberFormat: num })
  await xlsx.setStyle(wb, `Business Actuals!K6:K${businessEndRow}`, { numberFormat: num })
  await xlsx.setStyle(wb, `Business Actuals!L6:L${businessEndRow}`, { numberFormat: pct })
  await xlsx.setStyle(wb, `Personal Actuals!A6:A${personalEndRow}`, { numberFormat: 'mmm-yy' })
  await xlsx.setStyle(wb, `Personal Actuals!A6:H${personalEndRow}`, { fill: { color: '#FFFFFF' }, font: { color: '#000000' } })
  await xlsx.setStyle(wb, `Personal Actuals!D6:G${personalEndRow}`, { numberFormat: num })
  await xlsx.setStyle(wb, `Personal Actuals!A1:H1`, { fill: { color: '#1F3864' }, font: { color: '#FFFFFF', bold: true } })
  await xlsx.setStyle(wb, `Personal Actuals!A5:H5`, { fill: { color: '#4472C4' }, font: { color: '#FFFFFF', bold: true } })
  await xlsx.setSheetProperties(wb, 'Personal Actuals', { view: { showGridLines: false } })
  await xlsx.autoFitColumns(wb, 'Personal Actuals', ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'], { minWidth: 12, maxWidth: 40, padding: 2 })
  await xlsx.setStyle(wb, `Business Forecast!A51:A${forecastEndRow}`, { numberFormat: 'mmm-yy' })
  await xlsx.setStyle(wb, `Business Forecast!E51:E${forecastEndRow}`, { numberFormat: num })
  await xlsx.setStyle(wb, `Assets & Net Worth!A18:A${netWorthEndRow}`, { numberFormat: 'mmm-yy' })
  await xlsx.setStyle(wb, `Assets & Net Worth!D18:D${netWorthEndRow}`, { numberFormat: num })
  const recurringMeta = await xlsx.getListObject(wb, 'tblRecurring')
  const recurringEndRow = Number((recurringMeta.ref.match(/\d+$/) || ['6'])[0])
  await xlsx.setStyle(wb, `Recurring!E6:E${recurringEndRow}`, { numberFormat: num })
  await xlsx.setStyle(wb, `Recurring!G6:H${recurringEndRow}`, { numberFormat: 'mmm-yy' })
  await xlsx.setStyle(wb, `Recurring!I6:I${recurringEndRow}`, { numberFormat: pct })
  await xlsx.setStyle(wb, `Recurring!K6:K${recurringEndRow}`, { numberFormat: num })
  await xlsx.autoFitColumns(wb, 'Recurring', ['A','B','C','D','E','F','G','H','I','J','K','L'], { minWidth: 10, maxWidth: 42, padding: 2 })
  return { phase: input.phase, businessEndRow, personalEndRow, forecastEndRow, netWorthEndRow }
}

if (input.phase !== 'finish') return { phase: input.phase, skipped: true }
const businessMeta = await xlsx.getListObject(wb, 'tblBusinessActuals')
const personalMeta = await xlsx.getListObject(wb, 'tblPersonalMonthly')
const forecastMeta = await xlsx.getListObject(wb, 'tblBizForecastInputs')
const netWorthMeta = await xlsx.getListObject(wb, 'tblNetWorthSnapshots')
const businessEndRow = Number((businessMeta.ref.match(/\d+$/) || ['6'])[0])
const personalEndRow = Number((personalMeta.ref.match(/\d+$/) || ['6'])[0])
const forecastEndRow = Number((forecastMeta.ref.match(/\d+$/) || ['51'])[0])
const netWorthEndRow = Number((netWorthMeta.ref.match(/\d+$/) || ['18'])[0])
const clearCategoryCells = []
for (let row = 11; row <= 70; row++) {
  clearCategoryCells.push({ address: `'Setup & Checks'!H${row}`, value: null })
  clearCategoryCells.push({ address: `'Setup & Checks'!Q${row}`, value: null })
}
await xlsx.setCells(wb, clearCategoryCells)
await xlsx.setCells(wb, input.personal_categories.map((value, idx) => ({ address: `'Setup & Checks'!H${11 + idx}`, value })))
const combined = [...input.business_categories, ...input.personal_categories].filter((value, idx, all) => all.indexOf(value) === idx)
await xlsx.setCells(wb, combined.map((value, idx) => ({ address: `'Setup & Checks'!Q${11 + idx}`, value })))
for (const name of ['PersonalCategories', 'CombinedCategories']) {
  try { await xlsx.deleteDefinedName(wb, name) } catch (_) {}
}
await xlsx.addDefinedName(wb, 'PersonalCategories', `'Setup & Checks'!$H$11:$H$${10 + input.personal_categories.length}`)
await xlsx.addDefinedName(wb, 'CombinedCategories', `'Setup & Checks'!$Q$11:$Q$${10 + combined.length}`)

await xlsx.setDataValidations(wb, 'Business Actuals', [
  { address: `C6:C${businessEndRow}`, rule: { list: { source: '=BusinessFlowTypes', inCellDropDown: true } }, ignoreBlanks: true },
  { address: `D6:D${businessEndRow}`, rule: { list: { source: '=BusinessCategories', inCellDropDown: true } }, ignoreBlanks: true },
  { address: `H6:H${businessEndRow}`, rule: { list: { source: '=YesNo', inCellDropDown: true } }, ignoreBlanks: true },
])
await xlsx.setDataValidations(wb, 'Personal Actuals', [
  { address: `B6:B${personalEndRow}`, rule: { list: { source: '=PersonalTypes', inCellDropDown: true } }, ignoreBlanks: true },
  { address: `C6:C${personalEndRow}`, rule: { list: { source: '=PersonalCategories', inCellDropDown: true } }, ignoreBlanks: true },
])

const sheets = await xlsx.listSheets(wb)
if (!sheets.some(s => s.sheet === 'Import Status')) await xlsx.addSheet(wb, 'Import Status')
if (!sheets.some(s => s.sheet === 'Personal Forecast Baseline')) await xlsx.addSheet(wb, 'Personal Forecast Baseline')
if (!sheets.some(s => s.sheet === 'Business Forecast Baseline')) await xlsx.addSheet(wb, 'Business Forecast Baseline')
const statusRows = [
  ['STATEMENT PIPELINE STATUS', ''],
  ['Pipeline version', input.pipeline_version],
  ['State hash', input.state_hash],
  ['Cutoff date', input.cutoff_date],
  ['Business actual through', input.business_actual_through],
  ['Personal actual through', input.personal_actual_through],
  ['Timeline end', input.timeline_end],
  ['Personal transactions', input.status.personal_transaction_rows],
  ['Business transactions', input.status.business_transaction_rows],
  ['Personal source CSVs', input.status.personal_source_files],
  ['Business source CSVs', input.status.business_source_files],
  ['Personal coverage', input.status.personal_coverage],
  ['Business coverage', input.status.business_coverage],
  ['Low-confidence classifications', input.status.low_confidence],
  ['Validation failures', input.status.validation_failures],
  ['Workbook source tag', input.source_tag],
]
await xlsx.setCells(wb, statusRows.flatMap((row, idx) => [
  { address: `Import Status!A${idx + 1}`, value: row[0] },
  { address: `Import Status!B${idx + 1}`, value: row[1] },
]))
await xlsx.setStyle(wb, 'Import Status!A1:B1', { fill: { color: '#1F3864' }, font: { color: '#FFFFFF', bold: true } })
await xlsx.setStyle(wb, 'Import Status!A2:A16', { font: { bold: true } })
await xlsx.setSheetProperties(wb, 'Import Status', { view: { showGridLines: false } })
await xlsx.autoFitColumns(wb, 'Import Status', ['A', 'B'], { minWidth: 12, maxWidth: 50, padding: 2 })

const baselineCells = [
  { address: `'Personal Forecast Baseline'!A1`, value: 'PERSONAL VARIABLE EXPENSE BASELINE' },
  { address: `'Personal Forecast Baseline'!A2`, value: 'Category' },
  { address: `'Personal Forecast Baseline'!B2`, value: 'Trailing 6M average' },
]
input.personal_baselines.forEach((row, idx) => {
  baselineCells.push({ address: `'Personal Forecast Baseline'!A${idx + 3}`, value: row[0] })
  baselineCells.push({ address: `'Personal Forecast Baseline'!B${idx + 3}`, value: Number(row[1]), format: num })
})
await xlsx.setCells(wb, baselineCells)
await xlsx.setStyle(wb, `'Personal Forecast Baseline'!A1:B1`, { fill: { color: '#1F3864' }, font: { color: '#FFFFFF', bold: true } })
await xlsx.setStyle(wb, `'Personal Forecast Baseline'!A2:B2`, { fill: { color: '#D9EAF7' }, font: { bold: true } })
await xlsx.setSheetProperties(wb, 'Personal Forecast Baseline', { view: { showGridLines: false } })
await xlsx.autoFitColumns(wb, 'Personal Forecast Baseline', ['A', 'B'], { minWidth: 14, maxWidth: 40, padding: 2 })

const businessBaselineSheetCells = [
  { address: `'Business Forecast Baseline'!A1`, value: 'BUSINESS VARIABLE FORECAST BASELINE' },
  { address: `'Business Forecast Baseline'!A2`, value: 'Flow type' },
  { address: `'Business Forecast Baseline'!B2`, value: 'Category' },
  { address: `'Business Forecast Baseline'!C2`, value: 'Trailing 6M average' },
]
input.business_baselines.forEach((row, idx) => {
  businessBaselineSheetCells.push({ address: `'Business Forecast Baseline'!A${idx + 3}`, value: row[0] })
  businessBaselineSheetCells.push({ address: `'Business Forecast Baseline'!B${idx + 3}`, value: row[1] })
  businessBaselineSheetCells.push({ address: `'Business Forecast Baseline'!C${idx + 3}`, value: Number(row[2]), format: num })
})
await xlsx.setCells(wb, businessBaselineSheetCells)
await xlsx.setStyle(wb, `'Business Forecast Baseline'!A1:C1`, { fill: { color: '#1F3864' }, font: { color: '#FFFFFF', bold: true } })
await xlsx.setStyle(wb, `'Business Forecast Baseline'!A2:C2`, { fill: { color: '#D9EAF7' }, font: { bold: true } })
await xlsx.setSheetProperties(wb, 'Business Forecast Baseline', { view: { showGridLines: false } })
await xlsx.autoFitColumns(wb, 'Business Forecast Baseline', ['A', 'B', 'C'], { minWidth: 14, maxWidth: 40, padding: 2 })

await xlsx.setStyle(wb, `Business Actuals!A6:A${businessEndRow}`, { numberFormat: 'mmm-yy' })
await xlsx.setStyle(wb, `Business Actuals!E6:G${businessEndRow}`, { numberFormat: num })
await xlsx.setStyle(wb, `Business Actuals!K6:K${businessEndRow}`, { numberFormat: num })
await xlsx.setStyle(wb, `Business Actuals!L6:L${businessEndRow}`, { numberFormat: pct })
await xlsx.setStyle(wb, `Personal Actuals!A6:A${personalEndRow}`, { numberFormat: 'mmm-yy' })
await xlsx.setStyle(wb, `Personal Actuals!D6:G${personalEndRow}`, { numberFormat: num })
await xlsx.setStyle(wb, `Personal Actuals!A1:H1`, { fill: { color: '#1F3864' }, font: { color: '#FFFFFF', bold: true } })
await xlsx.setSheetProperties(wb, 'Personal Actuals', { view: { showGridLines: false } })
await xlsx.autoFitColumns(wb, 'Personal Actuals', ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'], { minWidth: 12, maxWidth: 40, padding: 2 })
await xlsx.setStyle(wb, `Business Forecast!A51:A${forecastEndRow}`, { numberFormat: 'mmm-yy' })
await xlsx.setStyle(wb, `Business Forecast!E51:E${forecastEndRow}`, { numberFormat: num })
await xlsx.setStyle(wb, `Assets & Net Worth!A18:A${netWorthEndRow}`, { numberFormat: 'mmm-yy' })
await xlsx.setStyle(wb, `Assets & Net Worth!D18:D${netWorthEndRow}`, { numberFormat: num })

return {
  phase: input.phase,
  businessEndRow,
  personalEndRow,
  forecastEndRow,
  netWorthEndRow,
  timelineMonths: input.timeline_months,
  sourceTag: input.source_tag,
}
