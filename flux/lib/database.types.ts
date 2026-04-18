export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  public: {
    Tables: {
      companies: {
        Row: {
          id: string
          name: string
          founder_email: string | null
          monthly_budget: number | null
          created_at: string
        }
        Insert: {
          id?: string
          name: string
          founder_email?: string | null
          monthly_budget?: number | null
          created_at?: string
        }
        Update: {
          id?: string
          name?: string
          founder_email?: string | null
          monthly_budget?: number | null
          created_at?: string
        }
        Relationships: []
      }
      employees: {
        Row: {
          id: string
          company_id: string
          name: string
          email: string
          role: string | null
          monthly_expense_cap: number | null
          created_at: string
        }
        Insert: {
          id?: string
          company_id: string
          name: string
          email: string
          role?: string | null
          monthly_expense_cap?: number | null
          created_at?: string
        }
        Update: {
          id?: string
          company_id?: string
          name?: string
          email?: string
          role?: string | null
          monthly_expense_cap?: number | null
          created_at?: string
        }
        Relationships: [
          {
            foreignKeyName: 'employees_company_id_fkey'
            columns: ['company_id']
            isOneToOne: false
            referencedRelation: 'companies'
            referencedColumns: ['id']
          },
        ]
      }
      transactions: {
        Row: {
          id: string
          company_id: string
          created_at: string
          merchant: string
          amount: number
          category: string | null
          submitted_by: string | null
          employee_id: string | null
          memo: string | null
          status: string | null
          pillar: string | null
          agent_assigned: string | null
          agent_reasoning: string | null
          agent_output: Json | null
          founder_action: string | null
          savings_identified: number | null
        }
        Insert: {
          id?: string
          company_id: string
          created_at?: string
          merchant: string
          amount: number
          category?: string | null
          submitted_by?: string | null
          employee_id?: string | null
          memo?: string | null
          status?: string | null
          pillar?: string | null
          agent_assigned?: string | null
          agent_reasoning?: string | null
          agent_output?: Json | null
          founder_action?: string | null
          savings_identified?: number | null
        }
        Update: {
          id?: string
          company_id?: string
          created_at?: string
          merchant?: string
          amount?: number
          category?: string | null
          submitted_by?: string | null
          employee_id?: string | null
          memo?: string | null
          status?: string | null
          pillar?: string | null
          agent_assigned?: string | null
          agent_reasoning?: string | null
          agent_output?: Json | null
          founder_action?: string | null
          savings_identified?: number | null
        }
        Relationships: [
          {
            foreignKeyName: 'transactions_company_id_fkey'
            columns: ['company_id']
            isOneToOne: false
            referencedRelation: 'companies'
            referencedColumns: ['id']
          },
          {
            foreignKeyName: 'transactions_employee_id_fkey'
            columns: ['employee_id']
            isOneToOne: false
            referencedRelation: 'employees'
            referencedColumns: ['id']
          },
        ]
      }
      seat_usage: {
        Row: {
          id: string
          company_id: string
          employee_id: string | null
          tool: string
          last_active_date: string | null
          confidence_score: number | null
          signal_sources: string[] | null
          commits_last_30d: number | null
          calendar_blocks: number | null
          gmail_notifications: number | null
          is_dormant: boolean | null
          checked_at: string
        }
        Insert: {
          id?: string
          company_id: string
          employee_id?: string | null
          tool: string
          last_active_date?: string | null
          confidence_score?: number | null
          signal_sources?: string[] | null
          commits_last_30d?: number | null
          calendar_blocks?: number | null
          gmail_notifications?: number | null
          is_dormant?: boolean | null
          checked_at?: string
        }
        Update: {
          id?: string
          company_id?: string
          employee_id?: string | null
          tool?: string
          last_active_date?: string | null
          confidence_score?: number | null
          signal_sources?: string[] | null
          commits_last_30d?: number | null
          calendar_blocks?: number | null
          gmail_notifications?: number | null
          is_dormant?: boolean | null
          checked_at?: string
        }
        Relationships: [
          {
            foreignKeyName: 'seat_usage_company_id_fkey'
            columns: ['company_id']
            isOneToOne: false
            referencedRelation: 'companies'
            referencedColumns: ['id']
          },
          {
            foreignKeyName: 'seat_usage_employee_id_fkey'
            columns: ['employee_id']
            isOneToOne: false
            referencedRelation: 'employees'
            referencedColumns: ['id']
          },
        ]
      }
      ai_usage: {
        Row: {
          id: string
          company_id: string
          week_start: string
          vendor: string | null
          model: string | null
          call_count: number | null
          total_tokens: number | null
          total_cost: number | null
          use_case: string | null
          recommended_model: string | null
          potential_savings: number | null
        }
        Insert: {
          id?: string
          company_id: string
          week_start: string
          vendor?: string | null
          model?: string | null
          call_count?: number | null
          total_tokens?: number | null
          total_cost?: number | null
          use_case?: string | null
          recommended_model?: string | null
          potential_savings?: number | null
        }
        Update: {
          id?: string
          company_id?: string
          week_start?: string
          vendor?: string | null
          model?: string | null
          call_count?: number | null
          total_tokens?: number | null
          total_cost?: number | null
          use_case?: string | null
          recommended_model?: string | null
          potential_savings?: number | null
        }
        Relationships: [
          {
            foreignKeyName: 'ai_usage_company_id_fkey'
            columns: ['company_id']
            isOneToOne: false
            referencedRelation: 'companies'
            referencedColumns: ['id']
          },
        ]
      }
      agent_alerts: {
        Row: {
          id: string
          company_id: string
          created_at: string
          transaction_id: string | null
          pillar: string | null
          alert_type: string | null
          message: string | null
          requires_action: boolean | null
          action_prompt: string | null
          resolved: boolean | null
          resolved_at: string | null
        }
        Insert: {
          id?: string
          company_id: string
          created_at?: string
          transaction_id?: string | null
          pillar?: string | null
          alert_type?: string | null
          message?: string | null
          requires_action?: boolean | null
          action_prompt?: string | null
          resolved?: boolean | null
          resolved_at?: string | null
        }
        Update: {
          id?: string
          company_id?: string
          created_at?: string
          transaction_id?: string | null
          pillar?: string | null
          alert_type?: string | null
          message?: string | null
          requires_action?: boolean | null
          action_prompt?: string | null
          resolved?: boolean | null
          resolved_at?: string | null
        }
        Relationships: [
          {
            foreignKeyName: 'agent_alerts_company_id_fkey'
            columns: ['company_id']
            isOneToOne: false
            referencedRelation: 'companies'
            referencedColumns: ['id']
          },
          {
            foreignKeyName: 'agent_alerts_transaction_id_fkey'
            columns: ['transaction_id']
            isOneToOne: false
            referencedRelation: 'transactions'
            referencedColumns: ['id']
          },
        ]
      }
      tool_overlaps: {
        Row: {
          id: string
          company_id: string
          category: string
          tools: string[]
          total_monthly_cost: number | null
          recommended_consolidation: string | null
          estimated_savings: number | null
          detected_at: string
          status: string | null
        }
        Insert: {
          id?: string
          company_id: string
          category: string
          tools: string[]
          total_monthly_cost?: number | null
          recommended_consolidation?: string | null
          estimated_savings?: number | null
          detected_at?: string
          status?: string | null
        }
        Update: {
          id?: string
          company_id?: string
          category?: string
          tools?: string[]
          total_monthly_cost?: number | null
          recommended_consolidation?: string | null
          estimated_savings?: number | null
          detected_at?: string
          status?: string | null
        }
        Relationships: [
          {
            foreignKeyName: 'tool_overlaps_company_id_fkey'
            columns: ['company_id']
            isOneToOne: false
            referencedRelation: 'companies'
            referencedColumns: ['id']
          },
        ]
      }
      subscription_renewals: {
        Row: {
          id: string
          company_id: string
          vendor: string
          plan_tier: string | null
          monthly_cost: number | null
          annual_cost: number | null
          billing_cycle: string | null
          renewal_date: string
          auto_renew: boolean | null
          notice_period_days: number | null
          contract_terms: string | null
          last_negotiated_date: string | null
          next_action_date: string | null
          priority: string | null
        }
        Insert: {
          id?: string
          company_id: string
          vendor: string
          plan_tier?: string | null
          monthly_cost?: number | null
          annual_cost?: number | null
          billing_cycle?: string | null
          renewal_date: string
          auto_renew?: boolean | null
          notice_period_days?: number | null
          contract_terms?: string | null
          last_negotiated_date?: string | null
          next_action_date?: string | null
          priority?: string | null
        }
        Update: {
          id?: string
          company_id?: string
          vendor?: string
          plan_tier?: string | null
          monthly_cost?: number | null
          annual_cost?: number | null
          billing_cycle?: string | null
          renewal_date?: string
          auto_renew?: boolean | null
          notice_period_days?: number | null
          contract_terms?: string | null
          last_negotiated_date?: string | null
          next_action_date?: string | null
          priority?: string | null
        }
        Relationships: [
          {
            foreignKeyName: 'subscription_renewals_company_id_fkey'
            columns: ['company_id']
            isOneToOne: false
            referencedRelation: 'companies'
            referencedColumns: ['id']
          },
        ]
      }
      plan_optimization: {
        Row: {
          id: string
          company_id: string
          vendor: string
          current_plan: string | null
          current_monthly_cost: number | null
          recommended_plan: string | null
          recommended_monthly_cost: number | null
          reason: string | null
          utilization_signals: Json | null
          confidence: number | null
          monthly_savings: number | null
          detected_at: string
          status: string | null
        }
        Insert: {
          id?: string
          company_id: string
          vendor: string
          current_plan?: string | null
          current_monthly_cost?: number | null
          recommended_plan?: string | null
          recommended_monthly_cost?: number | null
          reason?: string | null
          utilization_signals?: Json | null
          confidence?: number | null
          monthly_savings?: number | null
          detected_at?: string
          status?: string | null
        }
        Update: {
          id?: string
          company_id?: string
          vendor?: string
          current_plan?: string | null
          current_monthly_cost?: number | null
          recommended_plan?: string | null
          recommended_monthly_cost?: number | null
          reason?: string | null
          utilization_signals?: Json | null
          confidence?: number | null
          monthly_savings?: number | null
          detected_at?: string
          status?: string | null
        }
        Relationships: [
          {
            foreignKeyName: 'plan_optimization_company_id_fkey'
            columns: ['company_id']
            isOneToOne: false
            referencedRelation: 'companies'
            referencedColumns: ['id']
          },
        ]
      }
      feature_waste: {
        Row: {
          id: string
          company_id: string
          vendor: string
          feature: string
          monthly_cost: number | null
          usage_last_30d: number | null
          usage_last_90d: number | null
          first_enabled_date: string | null
          last_used_date: string | null
          recommendation: string | null
          confidence: number | null
          status: string | null
        }
        Insert: {
          id?: string
          company_id: string
          vendor: string
          feature: string
          monthly_cost?: number | null
          usage_last_30d?: number | null
          usage_last_90d?: number | null
          first_enabled_date?: string | null
          last_used_date?: string | null
          recommendation?: string | null
          confidence?: number | null
          status?: string | null
        }
        Update: {
          id?: string
          company_id?: string
          vendor?: string
          feature?: string
          monthly_cost?: number | null
          usage_last_30d?: number | null
          usage_last_90d?: number | null
          first_enabled_date?: string | null
          last_used_date?: string | null
          recommendation?: string | null
          confidence?: number | null
          status?: string | null
        }
        Relationships: [
          {
            foreignKeyName: 'feature_waste_company_id_fkey'
            columns: ['company_id']
            isOneToOne: false
            referencedRelation: 'companies'
            referencedColumns: ['id']
          },
        ]
      }
      shadow_it: {
        Row: {
          id: string
          company_id: string
          vendor: string
          first_charge_date: string | null
          monthly_cost: number | null
          charged_to_employee_id: string | null
          purpose_declared: string | null
          approved: boolean | null
          risk_level: string | null
          security_concerns: string[] | null
          detected_at: string
          status: string | null
        }
        Insert: {
          id?: string
          company_id: string
          vendor: string
          first_charge_date?: string | null
          monthly_cost?: number | null
          charged_to_employee_id?: string | null
          purpose_declared?: string | null
          approved?: boolean | null
          risk_level?: string | null
          security_concerns?: string[] | null
          detected_at?: string
          status?: string | null
        }
        Update: {
          id?: string
          company_id?: string
          vendor?: string
          first_charge_date?: string | null
          monthly_cost?: number | null
          charged_to_employee_id?: string | null
          purpose_declared?: string | null
          approved?: boolean | null
          risk_level?: string | null
          security_concerns?: string[] | null
          detected_at?: string
          status?: string | null
        }
        Relationships: [
          {
            foreignKeyName: 'shadow_it_company_id_fkey'
            columns: ['company_id']
            isOneToOne: false
            referencedRelation: 'companies'
            referencedColumns: ['id']
          },
          {
            foreignKeyName: 'shadow_it_charged_to_employee_id_fkey'
            columns: ['charged_to_employee_id']
            isOneToOne: false
            referencedRelation: 'employees'
            referencedColumns: ['id']
          },
        ]
      }
      savings_log: {
        Row: {
          id: string
          company_id: string
          title: string
          amount_monthly: number | null
          status: string
          source_type: string | null
          source_id: string | null
          created_at: string
        }
        Insert: {
          id?: string
          company_id: string
          title: string
          amount_monthly?: number | null
          status?: string
          source_type?: string | null
          source_id?: string | null
          created_at?: string
        }
        Update: {
          id?: string
          company_id?: string
          title?: string
          amount_monthly?: number | null
          status?: string
          source_type?: string | null
          source_id?: string | null
          created_at?: string
        }
        Relationships: [
          {
            foreignKeyName: 'savings_log_company_id_fkey'
            columns: ['company_id']
            isOneToOne: false
            referencedRelation: 'companies'
            referencedColumns: ['id']
          },
        ]
      }
    }
    Views: Record<string, never>
    Functions: Record<string, never>
    Enums: Record<string, never>
    CompositeTypes: Record<string, never>
  }
}
