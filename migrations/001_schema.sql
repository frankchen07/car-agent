CREATE TABLE IF NOT EXISTS vehicles (
    id SERIAL PRIMARY KEY,
    year INT NOT NULL,
    make VARCHAR(50) NOT NULL,
    model VARCHAR(50) NOT NULL,
    trim VARCHAR(50),
    engine VARCHAR(100),
    current_mileage INT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS service_events (
    id SERIAL PRIMARY KEY,
    vehicle_id INT REFERENCES vehicles(id),
    service_date DATE,
    mileage INT,
    servicer VARCHAR(100),
    description TEXT NOT NULL,
    interval_miles INT,
    next_due_mileage INT,
    source VARCHAR(50) DEFAULT 'checklist_import',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS maintenance_rules (
    id SERIAL PRIMARY KEY,
    vehicle_id INT REFERENCES vehicles(id),
    item VARCHAR(200) NOT NULL,
    category VARCHAR(50),
    anchor_mileage INT,
    interval_miles INT,
    due_mileage INT,
    priority VARCHAR(20),
    status VARCHAR(30) DEFAULT 'active',
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS oem_parts (
    id SERIAL PRIMARY KEY,
    vehicle_id INT REFERENCES vehicles(id),
    part_category VARCHAR(200) NOT NULL,
    part_number TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS issues (
    id SERIAL PRIMARY KEY,
    vehicle_id INT REFERENCES vehicles(id),
    logged_date DATE DEFAULT CURRENT_DATE,
    description TEXT NOT NULL,
    severity VARCHAR(20) DEFAULT 'medium',
    dtc_code VARCHAR(20),
    conditions TEXT,
    resolved BOOLEAN DEFAULT FALSE,
    resolution_notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
