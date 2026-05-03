-- CLIPSO.AI — Schema Supabase
-- Ejecutar en Supabase SQL Editor

-- Tabla: Proyectos del usuario
CREATE TABLE IF NOT EXISTS clipso_projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft',  -- draft, processing, completed, archived
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_clipso_projects_user ON clipso_projects(user_id);
CREATE INDEX IF NOT EXISTS idx_clipso_projects_status ON clipso_projects(status);

-- Tabla: Jobs de procesamiento
CREATE TABLE IF NOT EXISTS clipso_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID REFERENCES clipso_projects(id) ON DELETE CASCADE,
  user_id UUID NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',  -- queued, processing, completed, failed
  progress INTEGER DEFAULT 0,
  input_keys TEXT[] NOT NULL,
  output_key TEXT,
  preferences TEXT,
  error_message TEXT,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_clipso_jobs_user ON clipso_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_clipso_jobs_project ON clipso_jobs(project_id);
CREATE INDEX IF NOT EXISTS idx_clipso_jobs_status ON clipso_jobs(status);

-- Trigger: actualiza updated_at automáticamente
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_clipso_projects_updated ON clipso_projects;
CREATE TRIGGER trigger_clipso_projects_updated
  BEFORE UPDATE ON clipso_projects
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS trigger_clipso_jobs_updated ON clipso_jobs;
CREATE TRIGGER trigger_clipso_jobs_updated
  BEFORE UPDATE ON clipso_jobs
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- RLS desactivado por ahora (acceso vía API key del backend)
ALTER TABLE clipso_projects DISABLE ROW LEVEL SECURITY;
ALTER TABLE clipso_jobs DISABLE ROW LEVEL SECURITY;
