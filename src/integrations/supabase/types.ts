export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "14.5"
  }
  public: {
    Tables: {
      api_keys: {
        Row: {
          created_at: string
          id: string
          key_hash: string
          key_prefix: string
          last_used_at: string | null
          name: string
          revoked_at: string | null
          scopes: string[]
          user_id: string
        }
        Insert: {
          created_at?: string
          id?: string
          key_hash: string
          key_prefix: string
          last_used_at?: string | null
          name: string
          revoked_at?: string | null
          scopes?: string[]
          user_id: string
        }
        Update: {
          created_at?: string
          id?: string
          key_hash?: string
          key_prefix?: string
          last_used_at?: string | null
          name?: string
          revoked_at?: string | null
          scopes?: string[]
          user_id?: string
        }
        Relationships: []
      }
      camera_settings: {
        Row: {
          binning: number
          camera_id: string
          exposure_us: number
          extras: Json
          file_format: string
          gain: number
          id: string
          iso: number | null
          resolution: string
          updated_at: string
          white_balance: string
        }
        Insert: {
          binning?: number
          camera_id: string
          exposure_us?: number
          extras?: Json
          file_format?: string
          gain?: number
          id?: string
          iso?: number | null
          resolution?: string
          updated_at?: string
          white_balance?: string
        }
        Update: {
          binning?: number
          camera_id?: string
          exposure_us?: number
          extras?: Json
          file_format?: string
          gain?: number
          id?: string
          iso?: number | null
          resolution?: string
          updated_at?: string
          white_balance?: string
        }
        Relationships: [
          {
            foreignKeyName: "camera_settings_camera_id_fkey"
            columns: ["camera_id"]
            isOneToOne: true
            referencedRelation: "cameras"
            referencedColumns: ["id"]
          },
        ]
      }
      cameras: {
        Row: {
          adapter_type: Database["public"]["Enums"]["adapter_type"]
          connection_config: Json
          created_at: string
          id: string
          is_default: boolean
          model: string | null
          name: string
          status: Database["public"]["Enums"]["camera_status"]
          updated_at: string
        }
        Insert: {
          adapter_type?: Database["public"]["Enums"]["adapter_type"]
          connection_config?: Json
          created_at?: string
          id?: string
          is_default?: boolean
          model?: string | null
          name: string
          status?: Database["public"]["Enums"]["camera_status"]
          updated_at?: string
        }
        Update: {
          adapter_type?: Database["public"]["Enums"]["adapter_type"]
          connection_config?: Json
          created_at?: string
          id?: string
          is_default?: boolean
          model?: string | null
          name?: string
          status?: Database["public"]["Enums"]["camera_status"]
          updated_at?: string
        }
        Relationships: []
      }
      capture_jobs: {
        Row: {
          camera_id: string | null
          created_at: string
          ended_at: string | null
          error: string | null
          id: string
          params: Json
          started_at: string | null
          state: Database["public"]["Enums"]["capture_state"]
          type: string
        }
        Insert: {
          camera_id?: string | null
          created_at?: string
          ended_at?: string | null
          error?: string | null
          id?: string
          params?: Json
          started_at?: string | null
          state?: Database["public"]["Enums"]["capture_state"]
          type?: string
        }
        Update: {
          camera_id?: string | null
          created_at?: string
          ended_at?: string | null
          error?: string | null
          id?: string
          params?: Json
          started_at?: string | null
          state?: Database["public"]["Enums"]["capture_state"]
          type?: string
        }
        Relationships: [
          {
            foreignKeyName: "capture_jobs_camera_id_fkey"
            columns: ["camera_id"]
            isOneToOne: false
            referencedRelation: "cameras"
            referencedColumns: ["id"]
          },
        ]
      }
      capture_schedule: {
        Row: {
          camera_id: string | null
          daytime_protect: boolean
          enabled: boolean
          end_condition: string
          end_time: string | null
          id: string
          interval_seconds: number
          ramping: Json
          start_condition: string
          start_time: string | null
          updated_at: string
          weather_safe: boolean
        }
        Insert: {
          camera_id?: string | null
          daytime_protect?: boolean
          enabled?: boolean
          end_condition?: string
          end_time?: string | null
          id?: string
          interval_seconds?: number
          ramping?: Json
          start_condition?: string
          start_time?: string | null
          updated_at?: string
          weather_safe?: boolean
        }
        Update: {
          camera_id?: string | null
          daytime_protect?: boolean
          enabled?: boolean
          end_condition?: string
          end_time?: string | null
          id?: string
          interval_seconds?: number
          ramping?: Json
          start_condition?: string
          start_time?: string | null
          updated_at?: string
          weather_safe?: boolean
        }
        Relationships: [
          {
            foreignKeyName: "capture_schedule_camera_id_fkey"
            columns: ["camera_id"]
            isOneToOne: false
            referencedRelation: "cameras"
            referencedColumns: ["id"]
          },
        ]
      }
      images: {
        Row: {
          camera_id: string | null
          captured_at: string
          cloud_score: number | null
          created_at: string
          id: string
          metadata: Json
          processing_status: string
          star_count: number | null
          storage_path: string
          tags: string[]
          thumb_path: string | null
        }
        Insert: {
          camera_id?: string | null
          captured_at?: string
          cloud_score?: number | null
          created_at?: string
          id?: string
          metadata?: Json
          processing_status?: string
          star_count?: number | null
          storage_path: string
          tags?: string[]
          thumb_path?: string | null
        }
        Update: {
          camera_id?: string | null
          captured_at?: string
          cloud_score?: number | null
          created_at?: string
          id?: string
          metadata?: Json
          processing_status?: string
          star_count?: number | null
          storage_path?: string
          tags?: string[]
          thumb_path?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "images_camera_id_fkey"
            columns: ["camera_id"]
            isOneToOne: false
            referencedRelation: "cameras"
            referencedColumns: ["id"]
          },
        ]
      }
      logs: {
        Row: {
          context: Json
          id: string
          level: Database["public"]["Enums"]["log_level"]
          message: string
          source: string
          ts: string
        }
        Insert: {
          context?: Json
          id?: string
          level?: Database["public"]["Enums"]["log_level"]
          message: string
          source?: string
          ts?: string
        }
        Update: {
          context?: Json
          id?: string
          level?: Database["public"]["Enums"]["log_level"]
          message?: string
          source?: string
          ts?: string
        }
        Relationships: []
      }
      profiles: {
        Row: {
          created_at: string
          display_name: string | null
          id: string
          updated_at: string
          user_id: string
        }
        Insert: {
          created_at?: string
          display_name?: string | null
          id?: string
          updated_at?: string
          user_id: string
        }
        Update: {
          created_at?: string
          display_name?: string | null
          id?: string
          updated_at?: string
          user_id?: string
        }
        Relationships: []
      }
      realtime_events: {
        Row: {
          id: string
          payload: Json
          ts: string
          type: string
        }
        Insert: {
          id?: string
          payload?: Json
          ts?: string
          type: string
        }
        Update: {
          id?: string
          payload?: Json
          ts?: string
          type?: string
        }
        Relationships: []
      }
      system_settings: {
        Row: {
          api_enabled: boolean
          default_capture_interval_s: number
          default_image_format: string
          id: number
          latitude: number
          longitude: number
          observatory_name: string
          retention_days: number
          retention_max_disk_pct: number
          startup_auto_capture: boolean
          storage_path: string
          timelapse_path: string
          timezone: string
          updated_at: string
        }
        Insert: {
          api_enabled?: boolean
          default_capture_interval_s?: number
          default_image_format?: string
          id?: number
          latitude?: number
          longitude?: number
          observatory_name?: string
          retention_days?: number
          retention_max_disk_pct?: number
          startup_auto_capture?: boolean
          storage_path?: string
          timelapse_path?: string
          timezone?: string
          updated_at?: string
        }
        Update: {
          api_enabled?: boolean
          default_capture_interval_s?: number
          default_image_format?: string
          id?: number
          latitude?: number
          longitude?: number
          observatory_name?: string
          retention_days?: number
          retention_max_disk_pct?: number
          startup_auto_capture?: boolean
          storage_path?: string
          timelapse_path?: string
          timezone?: string
          updated_at?: string
        }
        Relationships: []
      }
      timelapse_jobs: {
        Row: {
          codec: string
          created_at: string
          date_from: string
          date_to: string
          error: string | null
          fps: number
          id: string
          name: string
          output_path: string | null
          progress: number
          state: Database["public"]["Enums"]["job_state"]
          updated_at: string
        }
        Insert: {
          codec?: string
          created_at?: string
          date_from: string
          date_to: string
          error?: string | null
          fps?: number
          id?: string
          name: string
          output_path?: string | null
          progress?: number
          state?: Database["public"]["Enums"]["job_state"]
          updated_at?: string
        }
        Update: {
          codec?: string
          created_at?: string
          date_from?: string
          date_to?: string
          error?: string | null
          fps?: number
          id?: string
          name?: string
          output_path?: string | null
          progress?: number
          state?: Database["public"]["Enums"]["job_state"]
          updated_at?: string
        }
        Relationships: []
      }
      user_roles: {
        Row: {
          created_at: string
          id: string
          role: Database["public"]["Enums"]["app_role"]
          user_id: string
        }
        Insert: {
          created_at?: string
          id?: string
          role: Database["public"]["Enums"]["app_role"]
          user_id: string
        }
        Update: {
          created_at?: string
          id?: string
          role?: Database["public"]["Enums"]["app_role"]
          user_id?: string
        }
        Relationships: []
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      has_role: {
        Args: {
          _role: Database["public"]["Enums"]["app_role"]
          _user_id: string
        }
        Returns: boolean
      }
    }
    Enums: {
      adapter_type:
        | "mock"
        | "libcamera"
        | "gphoto2"
        | "indi"
        | "zwo"
        | "webcam"
        | "custom"
      app_role: "admin" | "operator" | "viewer"
      camera_status: "connected" | "disconnected" | "error" | "unknown"
      capture_state:
        | "idle"
        | "scheduled"
        | "capturing"
        | "processing"
        | "error"
        | "stopped"
      job_state: "pending" | "running" | "complete" | "failed" | "cancelled"
      log_level: "debug" | "info" | "warning" | "error"
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  public: {
    Enums: {
      adapter_type: [
        "mock",
        "libcamera",
        "gphoto2",
        "indi",
        "zwo",
        "webcam",
        "custom",
      ],
      app_role: ["admin", "operator", "viewer"],
      camera_status: ["connected", "disconnected", "error", "unknown"],
      capture_state: [
        "idle",
        "scheduled",
        "capturing",
        "processing",
        "error",
        "stopped",
      ],
      job_state: ["pending", "running", "complete", "failed", "cancelled"],
      log_level: ["debug", "info", "warning", "error"],
    },
  },
} as const
