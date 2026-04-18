import type { RealtimePostgresChangesPayload } from '@supabase/supabase-js'
import type { Database } from './database.types'
import { supabase } from './supabase'

type Tables = Database['public']['Tables']

export type Company = Tables['companies']['Row']
export type Employee = Tables['employees']['Row']
export type Transaction = Tables['transactions']['Row']
export type SeatUsage = Tables['seat_usage']['Row']
export type AiUsage = Tables['ai_usage']['Row']
export type AgentAlert = Tables['agent_alerts']['Row']
export type ToolOverlap = Tables['tool_overlaps']['Row']
export type SubscriptionRenewal = Tables['subscription_renewals']['Row']
export type PlanOptimization = Tables['plan_optimization']['Row']
export type FeatureWaste = Tables['feature_waste']['Row']
export type ShadowIt = Tables['shadow_it']['Row']
export type SavingsLog = Tables['savings_log']['Row']

function supabaseErrorMessage(context: string, message: string | undefined): string {
  const detail = message?.trim().length ? message.trim() : 'Unknown Supabase error'
  return `${context}: ${detail}`
}

function assertOk<T>(context: string, result: { data: T | null; error: { message: string } | null }): NonNullable<T> {
  if (result.error) {
    throw new Error(supabaseErrorMessage(context, result.error.message))
  }
  if (result.data === null || result.data === undefined) {
    throw new Error(supabaseErrorMessage(context, 'Supabase returned no data'))
  }
  return result.data
}

function assertQuery<T>(context: string, result: { data: T | null; error: { message: string } | null }): T | null {
  if (result.error) {
    throw new Error(supabaseErrorMessage(context, result.error.message))
  }
  return result.data
}

function assertNoError(context: string, error: { message: string } | null): void {
  if (error) {
    throw new Error(supabaseErrorMessage(context, error.message))
  }
}

function toNumber(value: number | string | null | undefined): number {
  if (value == null) return 0
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function normalizeTransaction(row: Transaction): Transaction {
  return {
    ...row,
    amount: toNumber(row.amount as number | string | null | undefined),
    savings_identified: toNumber(row.savings_identified as number | string | null | undefined),
  }
}

function normalizeSeatUsage(row: SeatUsage): SeatUsage {
  return {
    ...row,
    confidence_score:
      row.confidence_score == null
        ? null
        : toNumber(row.confidence_score as number | string | null | undefined),
  }
}

function normalizeAiUsage(row: AiUsage): AiUsage {
  return {
    ...row,
    total_cost: row.total_cost == null ? null : toNumber(row.total_cost as number | string | null | undefined),
    potential_savings:
      row.potential_savings == null
        ? null
        : toNumber(row.potential_savings as number | string | null | undefined),
  }
}

function normalizeEmployee(row: Employee): Employee {
  return {
    ...row,
    monthly_expense_cap:
      row.monthly_expense_cap == null
        ? null
        : toNumber(row.monthly_expense_cap as number | string | null | undefined),
  }
}

function normalizeCompany(row: Company): Company {
  return {
    ...row,
    monthly_budget:
      row.monthly_budget == null ? null : toNumber(row.monthly_budget as number | string | null | undefined),
  }
}

function addUtcDays(isoDate: string, days: number): string {
  const d = new Date(`${isoDate}T12:00:00.000Z`)
  if (Number.isNaN(d.getTime())) {
    throw new Error(`addUtcDays: invalid date "${isoDate}"`)
  }
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

function todayUtcIsoDate(): string {
  return new Date().toISOString().slice(0, 10)
}

export async function logCharge(params: {
  companyId: string
  merchant: string
  amount: number
  memo?: string
}): Promise<{ transactionId: string }> {
  const insert: Tables['transactions']['Insert'] = {
    company_id: params.companyId,
    merchant: params.merchant,
    amount: params.amount,
    memo: params.memo ?? null,
    submitted_by: 'founder',
    status: 'pending',
    employee_id: null,
  }

  const result = await supabase.from('transactions').insert(insert).select('id').single()
  const data = assertOk('logCharge(insert transaction)', result)
  if (!data?.id) {
    throw new Error('logCharge: insert succeeded but no transaction id was returned')
  }
  return { transactionId: data.id }
}

export async function logExpense(params: {
  companyId: string
  employeeId: string
  merchant: string
  amount: number
  memo: string
}): Promise<{ transactionId: string }> {
  const insert: Tables['transactions']['Insert'] = {
    company_id: params.companyId,
    employee_id: params.employeeId,
    merchant: params.merchant,
    amount: params.amount,
    memo: params.memo,
    submitted_by: 'employee',
    status: 'pending',
  }

  const result = await supabase.from('transactions').insert(insert).select('id').single()
  const data = assertOk('logExpense(insert transaction)', result)
  if (!data?.id) {
    throw new Error('logExpense: insert succeeded but no transaction id was returned')
  }
  return { transactionId: data.id }
}

export async function respondToAlert(params: {
  alertId: string
  action: 'Y' | 'N'
}): Promise<{ success: boolean }> {
  const alertResult = await supabase
    .from('agent_alerts')
    .select('id, transaction_id')
    .eq('id', params.alertId)
    .maybeSingle()

  const alert = assertQuery('respondToAlert(load alert)', alertResult)
  if (!alert) {
    throw new Error(`respondToAlert: no alert found for id ${params.alertId}`)
  }

  const nowIso = new Date().toISOString()
  const updateAlertResult = await supabase
    .from('agent_alerts')
    .update({ resolved: true, resolved_at: nowIso })
    .eq('id', params.alertId)

  assertNoError('respondToAlert(update agent_alerts)', updateAlertResult.error)

  if (alert.transaction_id) {
    const updateTxnResult = await supabase
      .from('transactions')
      .update({ founder_action: params.action })
      .eq('id', alert.transaction_id)

    assertNoError('respondToAlert(update transactions)', updateTxnResult.error)
  }

  return { success: true }
}

export async function getRecentTransactions(companyId: string, limit = 20): Promise<Transaction[]> {
  const result = await supabase
    .from('transactions')
    .select('*')
    .eq('company_id', companyId)
    .order('created_at', { ascending: false })
    .limit(limit)

  const rows = assertOk('getRecentTransactions(select transactions)', result)
  return rows.map(normalizeTransaction)
}

export async function getPendingAlerts(companyId: string): Promise<AgentAlert[]> {
  const result = await supabase
    .from('agent_alerts')
    .select('*')
    .eq('company_id', companyId)
    .eq('resolved', false)
    .eq('requires_action', true)
    .order('created_at', { ascending: false })

  return assertOk('getPendingAlerts(select agent_alerts)', result)
}

export async function getSeatUsage(companyId: string, tool?: string): Promise<SeatUsage[]> {
  let query = supabase
    .from('seat_usage')
    .select('*')
    .eq('company_id', companyId)
    .order('tool', { ascending: true })
    .order('confidence_score', { ascending: false, nullsFirst: false })

  if (tool) {
    query = query.eq('tool', tool)
  }

  const result = await query
  const rows = assertOk('getSeatUsage(select seat_usage)', result)
  return rows.map(normalizeSeatUsage)
}

export async function getDormantSeats(companyId: string): Promise<SeatUsage[]> {
  const result = await supabase
    .from('seat_usage')
    .select('*')
    .eq('company_id', companyId)
    .eq('is_dormant', true)
    .order('tool', { ascending: true })
    .order('confidence_score', { ascending: true, nullsFirst: true })

  const rows = assertOk('getDormantSeats(select seat_usage)', result)
  return rows.map(normalizeSeatUsage)
}

export async function getAiUsageHistory(companyId: string, vendor?: string): Promise<AiUsage[]> {
  const eightWeeksAgo = new Date()
  eightWeeksAgo.setUTCDate(eightWeeksAgo.getUTCDate() - 56)
  const eightWeeksAgoIso = eightWeeksAgo.toISOString().slice(0, 10)

  let query = supabase
    .from('ai_usage')
    .select('*')
    .eq('company_id', companyId)
    .gte('week_start', eightWeeksAgoIso)
    .order('week_start', { ascending: false })

  if (vendor) {
    query = query.eq('vendor', vendor)
  }

  const result = await query
  const rows = assertOk('getAiUsageHistory(select ai_usage)', result)
  return rows.map(normalizeAiUsage)
}

export async function getEmployees(companyId: string): Promise<Employee[]> {
  const result = await supabase
    .from('employees')
    .select('*')
    .eq('company_id', companyId)
    .order('name', { ascending: true })

  const rows = assertOk('getEmployees(select employees)', result)
  return rows.map(normalizeEmployee)
}

export async function getCompany(companyId: string): Promise<Company> {
  const result = await supabase.from('companies').select('*').eq('id', companyId).maybeSingle()
  const row = assertQuery('getCompany(select companies)', result)
  if (!row) {
    throw new Error(`getCompany: no company found for id ${companyId}`)
  }
  return normalizeCompany(row)
}

export async function getTotalSavings(companyId: string): Promise<{
  thisMonth: number
  identified: number
  realized: number
}> {
  const result = await supabase
    .from('transactions')
    .select('savings_identified, status, created_at')
    .eq('company_id', companyId)

  const rows = assertOk('getTotalSavings(select transactions)', result)

  let identified = 0
  let realized = 0
  let thisMonth = 0

  const now = new Date()
  const monthStart = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1))

  for (const row of rows) {
    const savings = toNumber(row.savings_identified as number | string | null | undefined)
    identified += savings

    if (row.status === 'resolved') {
      realized += savings
      const createdAt = new Date(row.created_at)
      if (!Number.isNaN(createdAt.getTime()) && createdAt >= monthStart) {
        thisMonth += savings
      }
    }
  }

  return { thisMonth, identified, realized }
}

export function subscribeToTransactions(companyId: string, onInsert: (txn: Transaction) => void): () => void {
  const channelName = `public:transactions:${companyId}`
  const channel = supabase
    .channel(channelName)
    .on(
      'postgres_changes',
      {
        event: 'INSERT',
        schema: 'public',
        table: 'transactions',
        filter: `company_id=eq.${companyId}`,
      },
      (payload: RealtimePostgresChangesPayload<Transaction>) => {
        if (payload.eventType !== 'INSERT') return
        const row = payload.new
        if (!row) return
        onInsert(normalizeTransaction(row))
      }
    )
    .subscribe()

  return () => {
    void supabase.removeChannel(channel)
  }
}

export function subscribeToAlerts(companyId: string, onInsert: (alert: AgentAlert) => void): () => void {
  const channelName = `public:agent_alerts:${companyId}`
  const channel = supabase
    .channel(channelName)
    .on(
      'postgres_changes',
      {
        event: 'INSERT',
        schema: 'public',
        table: 'agent_alerts',
        filter: `company_id=eq.${companyId}`,
      },
      (payload: RealtimePostgresChangesPayload<AgentAlert>) => {
        if (payload.eventType !== 'INSERT') return
        const row = payload.new
        if (!row) return
        onInsert(row)
      }
    )
    .subscribe()

  return () => {
    void supabase.removeChannel(channel)
  }
}

// --- SaaS sprawl (overlaps, renewals, plans, waste, shadow IT) ---

export async function getToolOverlaps(
  companyId: string,
  status?: 'pending' | 'resolved' | 'dismissed'
): Promise<ToolOverlap[]> {
  let q = supabase
    .from('tool_overlaps')
    .select('*')
    .eq('company_id', companyId)
    .order('detected_at', { ascending: false })

  if (status) {
    q = q.eq('status', status)
  }

  return assertOk('getToolOverlaps', await q)
}

export async function getUpcomingRenewals(params: {
  companyId: string
  withinDays?: number
  priority?: 'critical' | 'high' | 'normal'
}): Promise<SubscriptionRenewal[]> {
  const withinDays = params.withinDays ?? 30
  const today = todayUtcIsoDate()
  const end = addUtcDays(today, withinDays)

  let q = supabase
    .from('subscription_renewals')
    .select('*')
    .eq('company_id', params.companyId)
    .gte('renewal_date', today)
    .lte('renewal_date', end)
    .order('renewal_date', { ascending: true })

  if (params.priority) {
    q = q.eq('priority', params.priority)
  }

  return assertOk('getUpcomingRenewals', await q)
}

export async function getCriticalRenewals(companyId: string): Promise<SubscriptionRenewal[]> {
  const today = todayUtcIsoDate()
  const end = addUtcDays(today, 14)

  const result = await supabase
    .from('subscription_renewals')
    .select('*')
    .eq('company_id', companyId)
    .not('next_action_date', 'is', null)
    .lte('next_action_date', end)
    .order('next_action_date', { ascending: true })

  return assertOk('getCriticalRenewals', result)
}

export async function getPlanOptimizations(companyId: string): Promise<PlanOptimization[]> {
  const result = await supabase
    .from('plan_optimization')
    .select('*')
    .eq('company_id', companyId)
    .eq('status', 'pending')
    .order('monthly_savings', { ascending: false, nullsFirst: false })

  return assertOk('getPlanOptimizations', result)
}

export async function getFeatureWaste(params: {
  companyId: string
  vendor?: string
  minMonthlyCost?: number
}): Promise<FeatureWaste[]> {
  let q = supabase
    .from('feature_waste')
    .select('*')
    .eq('company_id', params.companyId)
    .order('monthly_cost', { ascending: false, nullsFirst: false })

  if (params.vendor) {
    q = q.eq('vendor', params.vendor)
  }
  if (params.minMonthlyCost != null) {
    q = q.gte('monthly_cost', params.minMonthlyCost)
  }

  return assertOk('getFeatureWaste', await q)
}

export async function getShadowIt(params: {
  companyId: string
  riskLevel?: 'low' | 'medium' | 'high'
  status?: string
}): Promise<ShadowIt[]> {
  let q = supabase
    .from('shadow_it')
    .select('*')
    .eq('company_id', params.companyId)
    .order('detected_at', { ascending: false })

  if (params.riskLevel) {
    q = q.eq('risk_level', params.riskLevel)
  }
  if (params.status) {
    q = q.eq('status', params.status)
  }

  return assertOk('getShadowIt', await q)
}

export async function getSaasOverview(companyId: string): Promise<{
  totalMonthlyCost: number
  toolCount: number
  overlapsDetected: number
  upcomingRenewals: number
  optimizationsAvailable: number
  shadowItFound: number
  totalRecoverable: number
}> {
  const today = todayUtcIsoDate()
  const monthEnd = addUtcDays(today, 30)

  const [renewals, overlaps, plans, shadow, savingsRows] = await Promise.all([
    supabase.from('subscription_renewals').select('*').eq('company_id', companyId),
    supabase.from('tool_overlaps').select('id, status, estimated_savings').eq('company_id', companyId),
    supabase.from('plan_optimization').select('id, status, monthly_savings').eq('company_id', companyId),
    supabase.from('shadow_it').select('vendor, monthly_cost, status').eq('company_id', companyId),
    supabase.from('savings_log').select('amount_monthly, status').eq('company_id', companyId),
  ])

  const renewalList = assertOk('getSaasOverview(renewals)', renewals)
  const overlapList = assertOk('getSaasOverview(overlaps)', overlaps)
  const planList = assertOk('getSaasOverview(plans)', plans)
  const shadowList = assertOk('getSaasOverview(shadow)', shadow)
  const savingsList = assertOk('getSaasOverview(savings_log)', savingsRows)

  const totalMonthlyCost = renewalList.reduce((sum, r) => sum + toNumber(r.monthly_cost), 0)

  const vendorSet = new Set<string>()
  for (const r of renewalList) {
    vendorSet.add(r.vendor)
  }
  for (const s of shadowList) {
    if (s.status !== 'cancelled') vendorSet.add(s.vendor)
  }

  const overlapsDetected = overlapList.filter((o) => o.status === 'pending').length
  const upcomingRenewals = renewalList.filter((r) => r.renewal_date >= today && r.renewal_date <= monthEnd).length
  const optimizationsAvailable = planList.filter((p) => p.status === 'pending').length
  const shadowItFound = shadowList.filter((s) => s.status === 'flagged').length

  const totalRecoverable = savingsList
    .filter((s) => s.status === 'pending')
    .reduce((sum, s) => sum + toNumber(s.amount_monthly), 0)

  return {
    totalMonthlyCost,
    toolCount: vendorSet.size,
    overlapsDetected,
    upcomingRenewals,
    optimizationsAvailable,
    shadowItFound,
    totalRecoverable,
  }
}

export async function getSaasPillarSummary(companyId: string): Promise<{
  ghostSeats: { count: number; monthlySavings: number }
  zombieSubs: { count: number; monthlySavings: number }
  duplicates: { count: number; monthlySavings: number }
  tierOptimizations: { count: number; monthlySavings: number }
  featureWaste: { count: number; monthlySavings: number }
  shadowIt: { count: number; monthlySavings: number }
  upcomingRenewalValue: number
  totalRecoverable: number
}> {
  const today = todayUtcIsoDate()
  const monthEnd = addUtcDays(today, 30)

  const [seats, overlaps, plans, waste, shadow, renewals, savingsRows] = await Promise.all([
    supabase.from('seat_usage').select('tool, is_dormant').eq('company_id', companyId),
    supabase.from('tool_overlaps').select('estimated_savings, status').eq('company_id', companyId),
    supabase.from('plan_optimization').select('monthly_savings, status').eq('company_id', companyId),
    supabase.from('feature_waste').select('monthly_cost, recommendation, status').eq('company_id', companyId),
    supabase.from('shadow_it').select('monthly_cost, status').eq('company_id', companyId),
    supabase.from('subscription_renewals').select('monthly_cost, renewal_date').eq('company_id', companyId),
    supabase.from('savings_log').select('amount_monthly, status').eq('company_id', companyId),
  ])

  const seatRows = assertOk('getSaasPillarSummary(seat_usage)', seats)
  const overlapRows = assertOk('getSaasPillarSummary(tool_overlaps)', overlaps)
  const planRows = assertOk('getSaasPillarSummary(plan_optimization)', plans)
  const wasteRows = assertOk('getSaasPillarSummary(feature_waste)', waste)
  const shadowRows = assertOk('getSaasPillarSummary(shadow_it)', shadow)
  const renewalRows = assertOk('getSaasPillarSummary(subscription_renewals)', renewals)
  const savingsList = assertOk('getSaasPillarSummary(savings_log)', savingsRows)

  const dormantSeats = seatRows.filter((s) => s.is_dormant === true)
  const ghostCount = dormantSeats.length
  const ghostSavings = Math.round(ghostCount * 88)

  const toolNames = [...new Set(seatRows.map((s) => s.tool))]
  let zombieCount = 0
  let zombieSavings = 0
  for (const tool of toolNames) {
    const rowsForTool = seatRows.filter((s) => s.tool === tool)
    if (rowsForTool.length > 0 && rowsForTool.every((s) => s.is_dormant === true)) {
      zombieCount += 1
      zombieSavings += rowsForTool.length * 42
    }
  }

  const pendingOverlaps = overlapRows.filter((o) => o.status === 'pending')
  const duplicates = {
    count: pendingOverlaps.length,
    monthlySavings: pendingOverlaps.reduce((s, o) => s + toNumber(o.estimated_savings), 0),
  }

  const pendingPlans = planRows.filter((p) => p.status === 'pending')
  const tierOptimizations = {
    count: pendingPlans.length,
    monthlySavings: pendingPlans.reduce((s, p) => s + toNumber(p.monthly_savings), 0),
  }

  const wasteActive = wasteRows.filter(
    (w) =>
      w.status === 'open' &&
      w.recommendation != null &&
      w.recommendation !== 'keep'
  )
  const featureWaste = {
    count: wasteActive.length,
    monthlySavings: wasteActive.reduce((s, w) => s + toNumber(w.monthly_cost), 0),
  }

  const shadowFlagged = shadowRows.filter((x) => x.status === 'flagged')
  const shadowIt = {
    count: shadowFlagged.length,
    monthlySavings: shadowFlagged.reduce((s, x) => s + toNumber(x.monthly_cost), 0),
  }

  const upcomingRenewalValue = renewalRows
    .filter((r) => r.renewal_date >= today && r.renewal_date <= monthEnd)
    .reduce((s, r) => s + toNumber(r.monthly_cost), 0)

  const totalRecoverable = savingsList
    .filter((s) => s.status === 'pending')
    .reduce((s, x) => s + toNumber(x.amount_monthly), 0)

  return {
    ghostSeats: { count: ghostCount, monthlySavings: ghostSavings },
    zombieSubs: { count: zombieCount, monthlySavings: zombieSavings },
    duplicates,
    tierOptimizations,
    featureWaste,
    shadowIt,
    upcomingRenewalValue,
    totalRecoverable,
  }
}

export async function dismissToolOverlap(overlapId: string): Promise<{ success: boolean }> {
  const res = await supabase.from('tool_overlaps').update({ status: 'dismissed' }).eq('id', overlapId)
  assertNoError('dismissToolOverlap', res.error)
  return { success: true }
}

export async function approveShadowIt(params: {
  shadowItId: string
  migrate?: boolean
}): Promise<{ success: boolean }> {
  const existing = await supabase.from('shadow_it').select('purpose_declared').eq('id', params.shadowItId).maybeSingle()
  const row = assertQuery('approveShadowIt(load)', existing)
  if (!row) {
    throw new Error(`approveShadowIt: no shadow_it row for id ${params.shadowItId}`)
  }

  let purpose = row.purpose_declared
  if (params.migrate) {
    const suffix = ' [approved: migrate to company stack]'
    purpose = (purpose ?? '') + suffix
  }

  const res = await supabase
    .from('shadow_it')
    .update({ approved: true, status: 'approved', purpose_declared: purpose })
    .eq('id', params.shadowItId)

  assertNoError('approveShadowIt(update)', res.error)
  return { success: true }
}

export async function snoozeRenewal(params: { renewalId: string; days: number }): Promise<{ success: boolean }> {
  if (params.days < 1 || params.days > 365) {
    throw new Error('snoozeRenewal: days must be between 1 and 365')
  }

  const existing = await supabase
    .from('subscription_renewals')
    .select('next_action_date')
    .eq('id', params.renewalId)
    .maybeSingle()
  const row = assertQuery('snoozeRenewal(load)', existing)
  if (!row?.next_action_date) {
    throw new Error(`snoozeRenewal: renewal ${params.renewalId} has no next_action_date`)
  }

  const next = addUtcDays(row.next_action_date, params.days)
  const res = await supabase.from('subscription_renewals').update({ next_action_date: next }).eq('id', params.renewalId)
  assertNoError('snoozeRenewal(update)', res.error)
  return { success: true }
}

export async function markFeatureDisabled(featureWasteId: string): Promise<{ success: boolean }> {
  const res = await supabase.from('feature_waste').update({ status: 'disabled' }).eq('id', featureWasteId)
  assertNoError('markFeatureDisabled', res.error)
  return { success: true }
}
