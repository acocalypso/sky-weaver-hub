
-- ============ ENUMS ============
CREATE TYPE public.app_role AS ENUM ('admin', 'operator', 'viewer');
CREATE TYPE public.capture_state AS ENUM ('idle', 'scheduled', 'capturing', 'processing', 'error', 'stopped');
CREATE TYPE public.camera_status AS ENUM ('connected', 'disconnected', 'error', 'unknown');
CREATE TYPE public.adapter_type AS ENUM ('mock', 'libcamera', 'gphoto2', 'indi', 'zwo', 'webcam', 'custom');
CREATE TYPE public.job_state AS ENUM ('pending', 'running', 'complete', 'failed', 'cancelled');
CREATE TYPE public.log_level AS ENUM ('debug', 'info', 'warning', 'error');

-- ============ PROFILES ============
CREATE TABLE public.profiles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
  display_name TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.profiles TO authenticated;
GRANT ALL ON public.profiles TO service_role;
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Profiles are viewable by authenticated" ON public.profiles FOR SELECT TO authenticated USING (true);
CREATE POLICY "Users update own profile" ON public.profiles FOR UPDATE TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "Users insert own profile" ON public.profiles FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);

-- ============ USER ROLES ============
CREATE TABLE public.user_roles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  role public.app_role NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, role)
);
GRANT SELECT ON public.user_roles TO authenticated;
GRANT ALL ON public.user_roles TO service_role;
ALTER TABLE public.user_roles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view their roles" ON public.user_roles FOR SELECT TO authenticated USING (auth.uid() = user_id);

CREATE OR REPLACE FUNCTION public.has_role(_user_id UUID, _role public.app_role)
RETURNS BOOLEAN LANGUAGE SQL STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT EXISTS (SELECT 1 FROM public.user_roles WHERE user_id = _user_id AND role = _role)
$$;

-- updated_at helper
CREATE OR REPLACE FUNCTION public.tg_set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql SET search_path = public AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END $$;

-- Auto-create profile + grant admin to first user
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
  user_count INT;
BEGIN
  INSERT INTO public.profiles (user_id, display_name)
    VALUES (NEW.id, COALESCE(NEW.raw_user_meta_data->>'display_name', split_part(NEW.email, '@', 1)));
  SELECT COUNT(*) INTO user_count FROM auth.users;
  IF user_count = 1 THEN
    INSERT INTO public.user_roles (user_id, role) VALUES (NEW.id, 'admin');
  ELSE
    INSERT INTO public.user_roles (user_id, role) VALUES (NEW.id, 'viewer');
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ============ CAMERAS ============
CREATE TABLE public.cameras (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  model TEXT,
  adapter_type public.adapter_type NOT NULL DEFAULT 'mock',
  connection_config JSONB NOT NULL DEFAULT '{}'::jsonb,
  status public.camera_status NOT NULL DEFAULT 'unknown',
  is_default BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.cameras TO authenticated;
GRANT ALL ON public.cameras TO service_role;
ALTER TABLE public.cameras ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Cameras readable by all auth" ON public.cameras FOR SELECT TO authenticated USING (true);
CREATE POLICY "Admins manage cameras" ON public.cameras FOR ALL TO authenticated
  USING (public.has_role(auth.uid(), 'admin'))
  WITH CHECK (public.has_role(auth.uid(), 'admin'));
CREATE TRIGGER tg_cameras_updated BEFORE UPDATE ON public.cameras FOR EACH ROW EXECUTE FUNCTION public.tg_set_updated_at();

-- ============ CAMERA SETTINGS ============
CREATE TABLE public.camera_settings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  camera_id UUID NOT NULL UNIQUE REFERENCES public.cameras(id) ON DELETE CASCADE,
  exposure_us BIGINT NOT NULL DEFAULT 1000000,
  gain INT NOT NULL DEFAULT 100,
  iso INT,
  white_balance TEXT NOT NULL DEFAULT 'auto',
  binning INT NOT NULL DEFAULT 1,
  resolution TEXT NOT NULL DEFAULT '1920x1080',
  file_format TEXT NOT NULL DEFAULT 'jpg',
  extras JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.camera_settings TO authenticated;
GRANT ALL ON public.camera_settings TO service_role;
ALTER TABLE public.camera_settings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Camera settings readable" ON public.camera_settings FOR SELECT TO authenticated USING (true);
CREATE POLICY "Admins manage camera settings" ON public.camera_settings FOR ALL TO authenticated
  USING (public.has_role(auth.uid(), 'admin'))
  WITH CHECK (public.has_role(auth.uid(), 'admin'));
CREATE TRIGGER tg_camera_settings_updated BEFORE UPDATE ON public.camera_settings FOR EACH ROW EXECUTE FUNCTION public.tg_set_updated_at();

-- ============ CAPTURE JOBS ============
CREATE TABLE public.capture_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  camera_id UUID REFERENCES public.cameras(id) ON DELETE SET NULL,
  type TEXT NOT NULL DEFAULT 'manual',
  state public.capture_state NOT NULL DEFAULT 'idle',
  started_at TIMESTAMPTZ,
  ended_at TIMESTAMPTZ,
  error TEXT,
  params JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.capture_jobs TO authenticated;
GRANT ALL ON public.capture_jobs TO service_role;
ALTER TABLE public.capture_jobs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Capture jobs readable" ON public.capture_jobs FOR SELECT TO authenticated USING (true);
CREATE POLICY "Auth can insert capture jobs" ON public.capture_jobs FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Admins manage capture jobs" ON public.capture_jobs FOR ALL TO authenticated
  USING (public.has_role(auth.uid(), 'admin'))
  WITH CHECK (public.has_role(auth.uid(), 'admin'));

-- ============ SCHEDULE ============
CREATE TABLE public.capture_schedule (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  camera_id UUID REFERENCES public.cameras(id) ON DELETE CASCADE,
  enabled BOOLEAN NOT NULL DEFAULT true,
  start_condition TEXT NOT NULL DEFAULT 'astronomical_twilight',
  start_time TIME,
  end_condition TEXT NOT NULL DEFAULT 'astronomical_twilight',
  end_time TIME,
  interval_seconds INT NOT NULL DEFAULT 60,
  ramping JSONB NOT NULL DEFAULT '{"enabled": true, "min_exposure_us": 100, "max_exposure_us": 30000000}'::jsonb,
  weather_safe BOOLEAN NOT NULL DEFAULT false,
  daytime_protect BOOLEAN NOT NULL DEFAULT true,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.capture_schedule TO authenticated;
GRANT ALL ON public.capture_schedule TO service_role;
ALTER TABLE public.capture_schedule ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Schedule readable" ON public.capture_schedule FOR SELECT TO authenticated USING (true);
CREATE POLICY "Admins manage schedule" ON public.capture_schedule FOR ALL TO authenticated
  USING (public.has_role(auth.uid(), 'admin'))
  WITH CHECK (public.has_role(auth.uid(), 'admin'));
CREATE TRIGGER tg_schedule_updated BEFORE UPDATE ON public.capture_schedule FOR EACH ROW EXECUTE FUNCTION public.tg_set_updated_at();

-- ============ IMAGES ============
CREATE TABLE public.images (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  camera_id UUID REFERENCES public.cameras(id) ON DELETE SET NULL,
  captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  storage_path TEXT NOT NULL,
  thumb_path TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  tags TEXT[] NOT NULL DEFAULT '{}',
  star_count INT,
  cloud_score NUMERIC,
  processing_status TEXT NOT NULL DEFAULT 'ready',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_images_captured_at ON public.images (captured_at DESC);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.images TO authenticated;
GRANT ALL ON public.images TO service_role;
ALTER TABLE public.images ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Images readable" ON public.images FOR SELECT TO authenticated USING (true);
CREATE POLICY "Auth insert images" ON public.images FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Admins manage images" ON public.images FOR ALL TO authenticated
  USING (public.has_role(auth.uid(), 'admin'))
  WITH CHECK (public.has_role(auth.uid(), 'admin'));

-- ============ TIMELAPSE JOBS ============
CREATE TABLE public.timelapse_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  date_from DATE NOT NULL,
  date_to DATE NOT NULL,
  fps INT NOT NULL DEFAULT 30,
  codec TEXT NOT NULL DEFAULT 'h264',
  state public.job_state NOT NULL DEFAULT 'pending',
  progress INT NOT NULL DEFAULT 0,
  output_path TEXT,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.timelapse_jobs TO authenticated;
GRANT ALL ON public.timelapse_jobs TO service_role;
ALTER TABLE public.timelapse_jobs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Timelapse readable" ON public.timelapse_jobs FOR SELECT TO authenticated USING (true);
CREATE POLICY "Auth can insert timelapse" ON public.timelapse_jobs FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Admins manage timelapse" ON public.timelapse_jobs FOR ALL TO authenticated
  USING (public.has_role(auth.uid(), 'admin'))
  WITH CHECK (public.has_role(auth.uid(), 'admin'));
CREATE TRIGGER tg_timelapse_updated BEFORE UPDATE ON public.timelapse_jobs FOR EACH ROW EXECUTE FUNCTION public.tg_set_updated_at();

-- ============ SYSTEM SETTINGS (singleton) ============
CREATE TABLE public.system_settings (
  id INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  observatory_name TEXT NOT NULL DEFAULT 'My Observatory',
  latitude NUMERIC NOT NULL DEFAULT 37.7749,
  longitude NUMERIC NOT NULL DEFAULT -122.4194,
  timezone TEXT NOT NULL DEFAULT 'UTC',
  storage_path TEXT NOT NULL DEFAULT '/var/lib/allsky/images',
  timelapse_path TEXT NOT NULL DEFAULT '/var/lib/allsky/timelapses',
  default_capture_interval_s INT NOT NULL DEFAULT 60,
  default_image_format TEXT NOT NULL DEFAULT 'jpg',
  retention_days INT NOT NULL DEFAULT 30,
  retention_max_disk_pct INT NOT NULL DEFAULT 85,
  api_enabled BOOLEAN NOT NULL DEFAULT true,
  startup_auto_capture BOOLEAN NOT NULL DEFAULT true,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.system_settings TO authenticated;
GRANT ALL ON public.system_settings TO service_role;
ALTER TABLE public.system_settings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Settings readable" ON public.system_settings FOR SELECT TO authenticated USING (true);
CREATE POLICY "Admins update settings" ON public.system_settings FOR UPDATE TO authenticated
  USING (public.has_role(auth.uid(), 'admin'))
  WITH CHECK (public.has_role(auth.uid(), 'admin'));
CREATE TRIGGER tg_settings_updated BEFORE UPDATE ON public.system_settings FOR EACH ROW EXECUTE FUNCTION public.tg_set_updated_at();

-- ============ LOGS ============
CREATE TABLE public.logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  level public.log_level NOT NULL DEFAULT 'info',
  source TEXT NOT NULL DEFAULT 'system',
  message TEXT NOT NULL,
  context JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX idx_logs_ts ON public.logs (ts DESC);
GRANT SELECT, INSERT ON public.logs TO authenticated;
GRANT ALL ON public.logs TO service_role;
ALTER TABLE public.logs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Logs readable" ON public.logs FOR SELECT TO authenticated USING (true);
CREATE POLICY "Auth insert logs" ON public.logs FOR INSERT TO authenticated WITH CHECK (true);

-- ============ REALTIME EVENTS ============
CREATE TABLE public.realtime_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  type TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX idx_events_ts ON public.realtime_events (ts DESC);
GRANT SELECT, INSERT ON public.realtime_events TO authenticated;
GRANT ALL ON public.realtime_events TO service_role;
ALTER TABLE public.realtime_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Events readable" ON public.realtime_events FOR SELECT TO authenticated USING (true);
CREATE POLICY "Auth insert events" ON public.realtime_events FOR INSERT TO authenticated WITH CHECK (true);
ALTER PUBLICATION supabase_realtime ADD TABLE public.realtime_events;

-- ============ API KEYS ============
CREATE TABLE public.api_keys (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  key_prefix TEXT NOT NULL,
  key_hash TEXT NOT NULL UNIQUE,
  scopes TEXT[] NOT NULL DEFAULT '{"read:status"}',
  last_used_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.api_keys TO authenticated;
GRANT ALL ON public.api_keys TO service_role;
ALTER TABLE public.api_keys ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users manage own api keys" ON public.api_keys FOR ALL TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- ============ SEED DATA ============
INSERT INTO public.system_settings (id) VALUES (1);

INSERT INTO public.cameras (id, name, model, adapter_type, status, is_default)
VALUES ('11111111-1111-1111-1111-111111111111', 'Roof All-Sky', 'Mock ASI224MC', 'mock', 'connected', true);

INSERT INTO public.camera_settings (camera_id, exposure_us, gain, resolution, file_format)
VALUES ('11111111-1111-1111-1111-111111111111', 5000000, 250, '1920x1920', 'jpg');

INSERT INTO public.capture_schedule (camera_id, enabled) VALUES ('11111111-1111-1111-1111-111111111111', true);

-- Seed ~20 demo images using the bundled sample image path
DO $$
DECLARE i INT;
BEGIN
  FOR i IN 0..19 LOOP
    INSERT INTO public.images (camera_id, captured_at, storage_path, thumb_path, metadata, tags, star_count, cloud_score)
    VALUES (
      '11111111-1111-1111-1111-111111111111',
      now() - (i || ' hours')::interval,
      'demo/sample-sky-1.jpg',
      'demo/sample-sky-1.jpg',
      jsonb_build_object('exposure_us', 5000000, 'gain', 250, 'sky_temp_c', -3 + (i % 5)),
      ARRAY['demo','night'],
      120 + (i * 7) % 80,
      (i % 10) * 0.08
    );
  END LOOP;
END $$;

INSERT INTO public.logs (level, source, message) VALUES
  ('info', 'system', 'AllSky Control Hub started'),
  ('info', 'camera', 'Mock camera connected: Roof All-Sky'),
  ('info', 'scheduler', 'Scheduler armed for tonight'),
  ('warning', 'camera', 'Frame dropped: USB bandwidth saturated'),
  ('info', 'api', 'API server listening on /api/v1');

INSERT INTO public.realtime_events (type, payload) VALUES
  ('capture_started', '{"camera_id":"11111111-1111-1111-1111-111111111111"}'),
  ('new_image', '{"image_id":"demo"}');
