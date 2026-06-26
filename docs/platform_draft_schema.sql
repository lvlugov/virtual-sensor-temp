-- ============================================================
-- ENUMS (categorical fields from the data dictionary)
-- ============================================================
CREATE TYPE membership_role          AS ENUM ('admin', 'member', 'viewer');
CREATE TYPE client_status            AS ENUM ('active', 'suspended');
CREATE TYPE asset_class              AS ENUM ('PIPE','PRESSURE_VESSEL','HEAT_EXCHANGER','AIR_COOLER','STORAGE_TANK','COLUMN','REACTOR');
CREATE TYPE metallurgy_family        AS ENUM ('CARBON_STEEL','LOW_ALLOY_STEEL','AUSTENITIC_SS','DUPLEX_SS');
CREATE TYPE geometry_class           AS ENUM ('CYLINDRICAL_SHELL','ELBOW','SPHERICAL_SHELL','HEMISPHERICAL_HEAD','ELLIPTICAL_HEAD','TORISPHERICAL_HEAD','CONICAL_SHELL','NOZZLE','STRAIGHT_RUN');
CREATE TYPE geometry_complexity      AS ENUM ('SIMPLE','MODERATE','COMPLEX');
CREATE TYPE orientation              AS ENUM ('HORIZONTAL','VERTICAL','ANGLED');
CREATE TYPE exposure_zone            AS ENUM ('MARINE','TEMPERATE','ARID_DRY','SEVERE');
CREATE TYPE shelter_flag             AS ENUM ('PROTECTED','NORMAL','DAMAGED');
CREATE TYPE tracing_system           AS ENUM ('NONE','HIGH_INTEGRITY_STEAM_TRACED','MEDIUM_INTEGRITY_STEAM_TRACED','POOR_INTEGRITY_STEAM_TRACED','ELECTRIC_TRACED','HOT_OIL_TRACED');
CREATE TYPE insulation_material      AS ENUM ('FOAMGLASS','MINERAL_WOOL','FIBERGLASS','CALCIUM_SILICATE','PERLITE','ASBESTOS','UNKNOWN');
CREATE TYPE condition_band           AS ENUM ('BELOW_AVERAGE','AVERAGE','ABOVE_AVERAGE');
CREATE TYPE coating_system           AS ENUM ('TSA','IOZ','EPOXY_HT_MULTI','EPOXY_HT_SINGLE','BARE','UNKNOWN');
CREATE TYPE risk_band                AS ENUM ('LOW','MEDIUM','HIGH');
CREATE TYPE ingest_source            AS ENUM ('csv_upload','weather_api');
CREATE TYPE ingest_status            AS ENUM ('pending','processing','succeeded','failed');

-- ============================================================
-- TENANCY & USERS
-- ============================================================
CREATE TABLE clients (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            text NOT NULL UNIQUE,
    name            text NOT NULL,
    status          client_status NOT NULL DEFAULT 'active',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    entra_object_id text NOT NULL UNIQUE,             -- sub claim from Entra JWT
    email           text NOT NULL UNIQUE,
    full_name       text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE memberships (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    client_id       uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    role            membership_role NOT NULL DEFAULT 'member',
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, client_id)
);
CREATE INDEX idx_memberships_client ON memberships(client_id);

-- ============================================================
-- SITES
-- ============================================================
CREATE TABLE sites (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id       uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    name            text NOT NULL,
    location_text   text,                              -- free-form for pilot; lat/lng later
    latitude        numeric(8,5),                      -- needed for weather API lookup
    longitude       numeric(8,5),
    exposure_zone   exposure_zone NOT NULL,            -- site-level per data dictionary
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (client_id, name)
);
CREATE INDEX idx_sites_client ON sites(client_id);

-- ============================================================
-- ASSETS  (per data dictionary)
-- ============================================================
CREATE TABLE assets (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id                       uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    site_id                         uuid NOT NULL REFERENCES sites(id) ON DELETE RESTRICT,
    asset_tag                       text NOT NULL,         -- client's own identifier
    description                     text,

    -- Identification
    asset_class                     asset_class NOT NULL,
    asset_commissioning_date        date NOT NULL,
    component_diameter_mm           numeric(8,1) NOT NULL,
    furnished_thickness_mm          numeric(6,2) NOT NULL,

    -- Material
    metallurgy_family               metallurgy_family NOT NULL,

    -- Geometry
    most_prevalent_geometry_class   geometry_class NOT NULL,
    geometry_complexity             geometry_complexity NOT NULL DEFAULT 'MODERATE',
    orientation                     orientation NOT NULL,

    -- Environment & exposure (asset-level)
    sweating_asset                  boolean NOT NULL,
    shelter_flag                    shelter_flag NOT NULL DEFAULT 'NORMAL',

    -- Process conditions (design/spec values — static)
    spec_operating_temperature_c        numeric(6,1) NOT NULL,
    spec_min_operating_temperature_c    numeric(6,1),
    spec_max_operating_temperature_c    numeric(6,1),
    spec_avg_cycles_per_quarter         integer NOT NULL DEFAULT 0,
    spec_operation_vs_shutdown_fraction numeric(3,2) NOT NULL DEFAULT 1.00
        CHECK (spec_operation_vs_shutdown_fraction BETWEEN 0 AND 1),
    spec_tracing_system                 tracing_system NOT NULL,

    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now(),

    UNIQUE (client_id, asset_tag),
    CHECK (spec_max_operating_temperature_c IS NULL
           OR spec_max_operating_temperature_c >= spec_operating_temperature_c)
);
CREATE INDEX idx_assets_client   ON assets(client_id);
CREATE INDEX idx_assets_site     ON assets(site_id);

-- ============================================================
-- ASSET ATTRIBUTE RECORDS (semi-static / measured over time)
-- ============================================================
CREATE TABLE asset_process_conditions (
    id                              bigserial PRIMARY KEY,
    client_id                       uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    asset_id                        uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    recorded_at                     timestamptz NOT NULL,
    operating_temperature_c         numeric(6,1) NOT NULL,
    min_operating_temperature_c     numeric(6,1),
    max_operating_temperature_c     numeric(6,1),
    avg_cycles_per_quarter          integer NOT NULL DEFAULT 0,
    operation_vs_shutdown_fraction  numeric(3,2) NOT NULL DEFAULT 1.00
        CHECK (operation_vs_shutdown_fraction BETWEEN 0 AND 1),
    tracing_system                  tracing_system NOT NULL
);
CREATE INDEX idx_proc_cond_asset_time ON asset_process_conditions(asset_id, recorded_at DESC);
CREATE INDEX idx_proc_cond_client     ON asset_process_conditions(client_id);

CREATE TABLE asset_insulation_records (
    id                       bigserial PRIMARY KEY,
    client_id                uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    asset_id                 uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    recorded_at              timestamptz NOT NULL,
    insulation_material      insulation_material NOT NULL,
    insulation_thickness_mm  numeric(5,0) NOT NULL,
    insulation_install_date  date NOT NULL,
    insulation_condition     condition_band NOT NULL DEFAULT 'AVERAGE',
    cladding_integrity       condition_band NOT NULL,
    insulation_chloride_flag boolean NOT NULL DEFAULT false
);
CREATE INDEX idx_insulation_asset_time ON asset_insulation_records(asset_id, recorded_at DESC);
CREATE INDEX idx_insulation_client     ON asset_insulation_records(client_id);

CREATE TABLE asset_coating_records (
    id                       bigserial PRIMARY KEY,
    client_id                uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    asset_id                 uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    recorded_at              timestamptz NOT NULL,
    coating_system           coating_system NOT NULL,
    coating_application_date date
);
CREATE INDEX idx_coating_asset_time ON asset_coating_records(asset_id, recorded_at DESC);
CREATE INDEX idx_coating_client     ON asset_coating_records(client_id);

CREATE TABLE asset_inspection_records (
    id                           bigserial PRIMARY KEY,
    client_id                    uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    asset_id                     uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    recorded_at                  timestamptz NOT NULL,
    inspection_thickness_mm      numeric(6,2),
    latest_inspection_date       date,
    inspection_ever_done         boolean NOT NULL DEFAULT false,
    washdown_records_90d         integer NOT NULL DEFAULT 0
);
CREATE INDEX idx_inspection_asset_time ON asset_inspection_records(asset_id, recorded_at DESC);
CREATE INDEX idx_inspection_client     ON asset_inspection_records(client_id);

-- ============================================================
-- TIME SERIES
-- ============================================================
-- Process temperature uploaded per asset (T_process(t) in the dictionary).
-- Partition by month once volume warrants it; single table is fine for the pilot.
CREATE TABLE temperature_readings (
    id                  bigserial PRIMARY KEY,
    client_id           uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    asset_id            uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    recorded_at         timestamptz NOT NULL,
    temperature_c       numeric(6,2) NOT NULL,
    ingest_batch_id     uuid REFERENCES ingest_batches(id),
    UNIQUE (asset_id, recorded_at)
);
CREATE INDEX idx_temp_asset_time ON temperature_readings(asset_id, recorded_at DESC);
CREATE INDEX idx_temp_client      ON temperature_readings(client_id);

-- External weather feed, per site (T_ambient, RH, rainfall in the dictionary)
CREATE TABLE weather_readings (
    id                      bigserial PRIMARY KEY,
    client_id               uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    site_id                 uuid NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    recorded_at             timestamptz NOT NULL,
    ambient_temperature_c   numeric(5,1) NOT NULL,
    relative_humidity_pct   numeric(4,1) NOT NULL CHECK (relative_humidity_pct BETWEEN 0 AND 100),
    rainfall_mm_per_hr      numeric(5,1) NOT NULL DEFAULT 0,
    ingest_batch_id         uuid REFERENCES ingest_batches(id),
    UNIQUE (site_id, recorded_at)
);
CREATE INDEX idx_weather_site_time ON weather_readings(site_id, recorded_at DESC);
CREATE INDEX idx_weather_client     ON weather_readings(client_id);

-- ============================================================
-- PREDICTIONS
-- ============================================================
CREATE TABLE predictions (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id           uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    asset_id            uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    predicted_at        timestamptz NOT NULL DEFAULT now(),    -- when the run happened
    risk_score          numeric(4,3) NOT NULL CHECK (risk_score BETWEEN 0 AND 1),
    risk_band           risk_band NOT NULL,
    model_id            text NOT NULL,
    inputs_snapshot     jsonb NOT NULL                          -- inputs used, for reproducibility
);
CREATE INDEX idx_predictions_asset_time ON predictions(asset_id, predicted_at DESC);
CREATE INDEX idx_predictions_client     ON predictions(client_id);

-- ============================================================
-- OPERATIONAL
-- ============================================================
CREATE TABLE ingest_batches (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id           uuid REFERENCES clients(id) ON DELETE CASCADE,   -- null for system-wide weather pulls
    source              ingest_source NOT NULL,
    status              ingest_status NOT NULL DEFAULT 'pending',
    triggered_by_user_id uuid REFERENCES users(id),
    blob_path           text,                                            -- for CSV uploads
    target_table        text NOT NULL,                                   -- 'temperature_readings' | 'weather_readings' | 'assets'
    row_count           integer DEFAULT 0,
    error_count         integer DEFAULT 0,
    error_message       text,
    started_at          timestamptz,
    finished_at         timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_ingest_client_time ON ingest_batches(client_id, created_at DESC);
