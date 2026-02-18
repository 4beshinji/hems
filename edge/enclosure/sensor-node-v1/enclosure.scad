// ================================================================
// SOMS Environmental Sensor Node — Parametric Enclosure v1.0
// ================================================================
//
// Structure:  2-chamber thermal separation + decorative outer shell
//   Bottom:   Sensor chamber (MH-Z19C, BME680, PIR)
//   Barrier:  3mm solid + 5mm air gap (dead-air insulation)
//   Top:      MCU chamber (XIAO ESP32-C6)
//   Shell:    Decorative cover with vent patterns
//
// Airflow:    Bottom intake → sensors → barrier → MCU → top exhaust
// Connector:  JST-XH 2.5mm pitch (detachable)
// Print:      FDM, PETG recommended
//
// Orientation:
//   +Y = front (PIR window, faces room)
//   -Y = back  (wall-mount keyholes)
//   +X = right (USB-C exit)
//    Z = up    (exhaust)
// ================================================================

// ======================== RENDER TARGET ==========================
// Change to export individual STLs:
//   "assembly"     Full assembly (exploded, outer shell transparent)
//   "bottom"       Sensor chamber half  (print as-is, opening up)
//   "top"          MCU chamber half     (print flipped, ceiling on bed)
//   "top_fan"      MCU + 25mm fan mount (print flipped)
//   "shell"        Decorative outer cover
//   "pir_am312"    PIR adapter for AM312 mini sensor
//   "pir_hcsr501"  PIR mount for HC-SR501
//   "pir_blank"    Blank cap (no PIR)
part = "assembly";

// ======================== PARAMETERS ============================

// --- Print settings ---
wall    = 1.6;      // 0.4mm nozzle × 4 perimeters
tol     = 0.3;      // fit tolerance per side
layer   = 0.2;      // layer height
nozzle  = 0.4;      // nozzle diameter
$fn     = 48;

// --- Components [W, D, H] ---
// MH-Z19C CO2 sensor (NDIR, UART)
MHZ19       = [33, 20, 9];

// BME680 breakout board (I2C)
BME680      = [15, 12, 3];

// Seeed XIAO ESP32-C6
XIAO        = [21, 17.5, 3.5];     // board only
XIAO_USB    = [9, 7.5, 3.5];       // USB-C port opening
XIAO_PIN_H  = 2.5;                 // pin header height below board

// JST-XH 2.5mm pitch connector housings [W, D, H]
XH_PITCH    = 2.5;
XH_8P       = [22.5, 5.75, 7];     // 8-pin (inter-chamber harness)
XH_4P       = [12.5, 5.75, 7];     // 4-pin (BME680, MH-Z19C)
XH_3P       = [10.0, 5.75, 7];     // 3-pin (PIR)
XH_HDR_H    = 9;                    // through-hole header height

// PIR sensors
PIR_MOUNT_D = 35;                   // universal mount ring OD
AM312_D     = 10;                   // AM312 lens diameter
AM312_H     = 12;                   // AM312 body height
SR501_D     = 33;                   // HC-SR501 Fresnel lens OD
SR501_BOARD = [33, 24, 18];         // HC-SR501 total envelope

// 25mm 5V fan (optional exhaust)
FAN         = [25, 25, 7];
FAN_SCREW   = 20;                   // M2 mount hole spacing
FAN_BORE    = 22;                   // central airflow hole

// --- Chamber internals [W, D, H] ---
SENS_INT    = [52, 30, 22];         // sensor chamber
MCU_INT     = [52, 30, 17];         // MCU chamber

// --- Thermal barrier ---
BAR_SOLID   = 3;                    // solid wall thickness
BAR_AIR     = 5;                    // dead-air gap height
CABLE_PASS  = [16, 6];              // harness pass-through in barrier

// --- Chassis outer (derived) ---
CW = SENS_INT.x + 2 * wall;        // 55.2mm
CD = SENS_INT.y + 2 * wall;        // 33.2mm

// Half heights
BH = wall + SENS_INT.z + BAR_SOLID;             // bottom: 26.6mm
TH = MCU_INT.z + wall;                          // top:    18.6mm
TFH = MCU_INT.z + FAN.z + wall + 3;             // top+fan: 27.6mm
TOTAL_H = BH + BAR_AIR + TH;                    // total:  50.2mm

// --- M2 fasteners ---
M2_THRU     = 2.4;
M2_INSERT   = 3.2;                  // heat-set insert hole
M2_INS_DEP  = 4;                    // insert depth
M2_HEAD     = 4.2;                  // cap screw head
M2_HEAD_H   = 2.0;

// Boss positions — 4 corners, inset from chassis edges
BOSS_INSET  = 5.5;
BOSS = [
    [ CW/2 - BOSS_INSET,  CD/2 - BOSS_INSET],
    [-CW/2 + BOSS_INSET,  CD/2 - BOSS_INSET],
    [ CW/2 - BOSS_INSET, -CD/2 + BOSS_INSET],
    [-CW/2 + BOSS_INSET, -CD/2 + BOSS_INSET]
];

// --- Wall mount (back face) ---
KH_BIG      = 6;                    // keyhole large hole (screw head)
KH_SLOT     = 3.5;                  // keyhole slot width (shaft)
KH_SPACE    = 30;                   // center-to-center distance

// --- Ventilation ---
VSLOT_W     = 2.0;                  // slot width
VSLOT_GAP   = 3.5;                  // slot spacing

// --- Outer shell ---
SH_GAP      = 4;                    // chassis-to-shell clearance
SH_WALL     = 1.6;                  // shell wall thickness
SH_R        = 4;                    // corner radius
SH_W  = CW + 2 * (SH_GAP + SH_WALL);
SH_D  = CD + 2 * (SH_GAP + SH_WALL);
SH_H  = TOTAL_H + SH_GAP + 10;     // extra height for visual balance

// ======================== DIMENSION REPORT =======================
echo("=== Chassis dimensions ===");
echo(str("  Width:  ", CW, " mm"));
echo(str("  Depth:  ", CD, " mm"));
echo(str("  Height: ", TOTAL_H, " mm (no fan)"));
echo(str("  Height: ", BH + BAR_AIR + TFH, " mm (with fan)"));
echo("=== Shell dimensions ===");
echo(str("  Width:  ", SH_W, " mm"));
echo(str("  Depth:  ", SH_D, " mm"));
echo(str("  Height: ", SH_H, " mm"));

// ======================== UTILITIES ==============================

// Rounded box — centered on XY, Z starts at 0
module rbox(size, r = 2) {
    hull()
        for (sx = [-1, 1], sy = [-1, 1])
            translate([sx * (size.x/2 - r), sy * (size.y/2 - r), 0])
                cylinder(r = r, h = size.z);
}

// Linear slot array — centered, slots along X axis
// Cuts through Y (use rotate to orient before calling)
module slot_array(span, slot_w, slot_h, slot_depth = 10) {
    n = max(1, floor(span / (slot_w + VSLOT_GAP)));
    total = n * slot_w + (n - 1) * VSLOT_GAP;
    x0 = -total / 2 + slot_w / 2;
    for (i = [0 : n - 1])
        translate([x0 + i * (slot_w + VSLOT_GAP), 0, 0])
            cube([slot_w, slot_depth, slot_h], center = true);
}

// Hexagonal ventilation grid — centered on XY, extrudes in Z
module hex_grid(w, h, hex_r = 2.5, pitch = 7) {
    dx = pitch * 1.5;
    dy = pitch * sin(60);
    for (cx = [-ceil(w / dx / 2) : ceil(w / dx / 2)])
        for (cy = [-ceil(h / dy / 2) : ceil(h / dy / 2)]) {
            px = cx * dx;
            py = cy * dy + (abs(cx) % 2) * dy / 2;
            if (abs(px) < w/2 - hex_r && abs(py) < h/2 - hex_r)
                translate([px, py, 0])
                    cylinder(r = hex_r, h = wall * 3, center = true, $fn = 6);
        }
}

// Keyhole profile (2D) — large circle + vertical slot
module keyhole_2d(d_big, d_slot) {
    circle(d = d_big);
    translate([d_big * 0.35, 0])
        circle(d = d_slot);
    translate([0, -d_slot / 2])
        square([d_big * 0.7, d_slot]);
}

// Wall vent pattern — cuts through a face at given Z range
module face_vents(face_w, z_lo, z_hi, depth = 10) {
    vent_h = z_hi - z_lo;
    z_mid = (z_lo + z_hi) / 2;
    translate([0, 0, z_mid])
        slot_array(face_w - 12, VSLOT_W, vent_h - 6, depth);
}


// ======================== BOTTOM HALF ============================
// Sensor chamber + thermal barrier ceiling
// Print as-is: flat bottom on bed, cavity opening faces up

module bottom_half() {
    difference() {
        // --- Solid body ---
        rbox([CW, CD, BH]);

        // --- Sensor chamber cavity ---
        translate([0, 0, wall])
            rbox([SENS_INT.x, SENS_INT.y, SENS_INT.z + 0.1], r = 1);

        // --- Side vents (left -X, right +X walls) ---
        for (sx = [-1, 1])
            translate([sx * CW / 2, 0, 0])
                rotate([0, 0, 0])
                face_vents(SENS_INT.y - 4,
                           wall + 4, wall + SENS_INT.z - 4,
                           wall + 2);

        // --- Front/back vents (+Y, -Y walls) ---
        // Back: full vents
        translate([0, -CD / 2, 0])
            rotate([0, 0, 90])
            face_vents(SENS_INT.x - 4,
                       wall + 4, wall + SENS_INT.z - 4,
                       wall + 2);
        // Front: vents avoiding PIR mount zone (±PIR_MOUNT_D/2)
        pir_z = wall + SENS_INT.z * 0.55;
        for (dx = [-1, 1])
            translate([dx * (PIR_MOUNT_D / 2 + 8), CD / 2, 0])
                face_vents(8,
                           wall + 4, wall + SENS_INT.z - 4,
                           wall + 2);

        // --- PIR mount hole (front face +Y) ---
        translate([0, CD / 2 - wall - 0.1, pir_z])
            rotate([-90, 0, 0])
            cylinder(d = PIR_MOUNT_D + tol * 2, h = wall + 0.2);
        // Retention groove (1.2mm deep ring inside wall)
        translate([0, CD / 2 - 1.2, pir_z])
            rotate([-90, 0, 0])
            difference() {
                cylinder(d = PIR_MOUNT_D + 2.5, h = 1.2);
                translate([0, 0, -0.1])
                    cylinder(d = PIR_MOUNT_D - 0.5, h = 1.4);
            }

        // --- Cable pass-through (barrier ceiling) ---
        translate([0, 0, BH - BAR_SOLID / 2])
            cube([CABLE_PASS.x, CABLE_PASS.y, BAR_SOLID + 0.2],
                 center = true);

        // --- M2 heat-set insert holes (top of barrier) ---
        for (p = BOSS)
            translate([p.x, p.y, BH - M2_INS_DEP])
                cylinder(d = M2_INSERT, h = M2_INS_DEP + 0.1);

        // --- Keyholes (back face -Y) ---
        for (dx = [-KH_SPACE / 2, KH_SPACE / 2])
            translate([dx, -CD / 2 - 0.1, BH * 0.45])
                rotate([90, 0, 0])
                rotate([0, 0, 90])
                linear_extrude(wall + 0.2)
                    keyhole_2d(KH_BIG, KH_SLOT);

        // --- Bottom cable routing channel (USB-C from MCU above) ---
        translate([CW / 2 - wall / 2, 0, -0.1])
            cube([wall + 0.2, 7, wall + 0.2], center = true);
    }

    // --- MH-Z19C mount posts (4 corners) ---
    // Positioned left-of-center to leave room for BME680 on the right
    mhz_cx = -SENS_INT.x / 4 + 2;
    for (dx = [-1, 1], dy = [-1, 1])
        translate([mhz_cx + dx * (MHZ19.x / 2 - 1.5),
                   dy * (MHZ19.y / 2 - 1.5),
                   wall])
            difference() {
                cylinder(d = 3.5, h = 3, $fn = 20);
                translate([0, 0, -0.1])
                    cylinder(d = 1.8, h = 3.2, $fn = 20);
            }

    // --- BME680 mount ledge (right side of chamber) ---
    bme_cx = SENS_INT.x / 4;
    bme_cy = 0;
    for (dy = [-1, 1])
        translate([bme_cx - BME680.x / 2 - 1,
                   bme_cy + dy * (BME680.y / 2 + 0.3) - 0.75,
                   wall])
            cube([BME680.x + 2, 1.5, BME680.z + 1]);

    // --- XH header mount shelves (sensor side of harness) ---
    // Small shelf near barrier cable hole for XH-8P header
    translate([-XH_8P.x / 2, -CABLE_PASS.y / 2 - 2, wall + SENS_INT.z - 3])
        cube([XH_8P.x, 2, 3]);
}


// ======================== TOP HALF ===============================
// MCU chamber + standoff posts for air gap
// Print flipped: rotate([180,0,0]) so ceiling is on bed

module top_half() {
    difference() {
        union() {
            // --- Main body ---
            rbox([CW, CD, TH]);

            // --- Standoff posts (extend below, create air gap) ---
            for (p = BOSS)
                translate([p.x, p.y, -BAR_AIR])
                    cylinder(d = M2_THRU + 4.5, h = BAR_AIR + 0.01, $fn = 20);
        }

        // --- MCU chamber cavity ---
        translate([0, 0, -0.01])
            rbox([MCU_INT.x, MCU_INT.y, MCU_INT.z + 0.01], r = 1);

        // --- Top hex ventilation ---
        translate([0, 0, TH - wall / 2])
            hex_grid(CW - 12, CD - 12, hex_r = 2.5, pitch = 7);

        // --- Side vents (left/right walls) ---
        for (sx = [-1, 1])
            translate([sx * CW / 2, 0, 0])
                face_vents(MCU_INT.y - 4,
                           3, MCU_INT.z - 3,
                           wall + 2);

        // --- USB-C port cutout (right side +X) ---
        usb_z = XIAO_PIN_H + XIAO.z / 2;
        translate([CW / 2 - wall / 2, 0, usb_z])
            cube([wall + 1, XIAO_USB.x + 2, XIAO_USB.z + 2],
                 center = true);

        // --- M2 through holes + countersink (in standoffs) ---
        for (p = BOSS) {
            // Through hole full length
            translate([p.x, p.y, -BAR_AIR - 0.1])
                cylinder(d = M2_THRU, h = BAR_AIR + TH + 0.2);
            // Countersink from bottom of standoff
            translate([p.x, p.y, -BAR_AIR - 0.1])
                cylinder(d = M2_HEAD, h = M2_HEAD_H + 0.1);
        }

        // --- Harness entry from below (matches barrier cable hole) ---
        translate([0, 0, -0.1])
            cube([CABLE_PASS.x + 2, CABLE_PASS.y + 2, 3], center = true);
    }

    // --- XIAO mounting rails ---
    // XIAO placed with USB-C facing +X wall
    // Board length (21mm) along X, width (17.5mm) along Y
    xiao_cx = CW / 2 - wall - XIAO.x / 2 - 1;
    for (dy = [-1, 1])
        translate([xiao_cx - XIAO.x / 2 - 0.5,
                   dy * (XIAO.y / 2 + 0.5) - 0.6,
                   0])
            cube([XIAO.x + 1, 1.2, XIAO_PIN_H]);

    // --- XH-8P header mount (MCU side of harness) ---
    translate([-XH_8P.x / 2, -CABLE_PASS.y / 2 - 2, 0])
        cube([XH_8P.x, 2, 3]);
}


// ======================== TOP HALF (FAN) =========================
// MCU chamber + 25mm fan mount
// Print flipped: ceiling on bed

module top_fan_half() {
    difference() {
        union() {
            rbox([CW, CD, TFH]);

            for (p = BOSS)
                translate([p.x, p.y, -BAR_AIR])
                    cylinder(d = M2_THRU + 4.5, h = BAR_AIR + 0.01, $fn = 20);
        }

        // MCU chamber cavity
        translate([0, 0, -0.01])
            rbox([MCU_INT.x, MCU_INT.y, MCU_INT.z + 0.01], r = 1);

        // Fan recess (above MCU chamber)
        translate([-FAN.x / 2 - 0.5, -FAN.y / 2 - 0.5, MCU_INT.z])
            cube([FAN.x + 1, FAN.y + 1, FAN.z + 1]);

        // Fan exhaust hole (through ceiling)
        translate([0, 0, TFH - wall - 0.5])
            cylinder(d = FAN_BORE, h = wall + 1);

        // Fan M2 mount holes (4 corners)
        for (sx = [-1, 1], sy = [-1, 1])
            translate([sx * FAN_SCREW / 2, sy * FAN_SCREW / 2, MCU_INT.z - 0.1])
                cylinder(d = M2_THRU, h = FAN.z + wall + 4);

        // Protective grille rings around fan hole (top face)
        translate([0, 0, TFH - wall / 2])
            for (r = [3, 6, 9])
                difference() {
                    cylinder(r = r + 0.6, h = wall + 1, center = true);
                    cylinder(r = r, h = wall + 2, center = true);
                }

        // Side vents
        for (sx = [-1, 1])
            translate([sx * CW / 2, 0, 0])
                face_vents(MCU_INT.y - 4, 3, MCU_INT.z - 3, wall + 2);

        // USB-C port
        usb_z = XIAO_PIN_H + XIAO.z / 2;
        translate([CW / 2 - wall / 2, 0, usb_z])
            cube([wall + 1, XIAO_USB.x + 2, XIAO_USB.z + 2], center = true);

        // M2 through holes + countersink
        for (p = BOSS) {
            translate([p.x, p.y, -BAR_AIR - 0.1])
                cylinder(d = M2_THRU, h = BAR_AIR + TFH + 0.2);
            translate([p.x, p.y, -BAR_AIR - 0.1])
                cylinder(d = M2_HEAD, h = M2_HEAD_H + 0.1);
        }

        // Harness entry
        translate([0, 0, -0.1])
            cube([CABLE_PASS.x + 2, CABLE_PASS.y + 2, 3], center = true);
    }

    // XIAO mounting rails (same as non-fan)
    xiao_cx = CW / 2 - wall - XIAO.x / 2 - 1;
    for (dy = [-1, 1])
        translate([xiao_cx - XIAO.x / 2 - 0.5,
                   dy * (XIAO.y / 2 + 0.5) - 0.6,
                   0])
            cube([XIAO.x + 1, 1.2, XIAO_PIN_H]);
}


// ======================== OUTER SHELL ============================
// Decorative cover — slides over chassis from above
// Open bottom for cable exit
// Vent density: exhaust (upper) > intake (lower)

module outer_shell() {
    pir_z_in_shell = SH_GAP + wall + SENS_INT.z * 0.55;
    usb_z_in_shell = SH_GAP + BH + BAR_AIR + XIAO_PIN_H + XIAO.z / 2;

    difference() {
        // --- Outer form ---
        rbox([SH_W, SH_D, SH_H], r = SH_R);

        // --- Inner cavity (open at z=0 bottom) ---
        translate([0, 0, -0.1])
            rbox([SH_W - 2 * SH_WALL, SH_D - 2 * SH_WALL, SH_H + 1],
                 r = max(SH_R - SH_WALL, 1));

        // --- Top hex exhaust ---
        translate([0, 0, SH_H - SH_WALL / 2])
            hex_grid(SH_W - 2 * SH_R - 2, SH_D - 2 * SH_R - 2,
                     hex_r = 3, pitch = 8);

        // --- Exhaust louvers (upper 35%, all 4 sides) ---
        for (z = [SH_H * 0.62 : 4.5 : SH_H - 5]) {
            for (sy = [-1, 1])   // front/back
                translate([0, sy * SH_D / 2, z])
                    rotate([90, 0, 0])
                    hull() for (dx = [-1, 1])
                        translate([dx * (SH_W / 2 - SH_R - 4), 0, 0])
                            cylinder(d = VSLOT_W, h = SH_WALL + 1,
                                     center = true, $fn = 8);
            for (sx = [-1, 1])   // left/right
                translate([sx * SH_W / 2, 0, z])
                    rotate([0, 90, 0])
                    hull() for (dy = [-1, 1])
                        translate([0, dy * (SH_D / 2 - SH_R - 4), 0])
                            cylinder(d = VSLOT_W, h = SH_WALL + 1,
                                     center = true, $fn = 8);
        }

        // --- Intake louvers (lower 28%, wider spacing) ---
        for (z = [5 : 6 : SH_H * 0.28]) {
            for (sy = [-1, 1])
                translate([0, sy * SH_D / 2, z])
                    rotate([90, 0, 0])
                    hull() for (dx = [-1, 1])
                        translate([dx * (SH_W / 2 - SH_R - 6), 0, 0])
                            cylinder(d = VSLOT_W, h = SH_WALL + 1,
                                     center = true, $fn = 8);
            for (sx = [-1, 1])
                translate([sx * SH_W / 2, 0, z])
                    rotate([0, 90, 0])
                    hull() for (dy = [-1, 1])
                        translate([0, dy * (SH_D / 2 - SH_R - 6), 0])
                            cylinder(d = VSLOT_W, h = SH_WALL + 1,
                                     center = true, $fn = 8);
        }

        // --- PIR window (front face +Y) ---
        translate([0, SH_D / 2 - SH_WALL / 2, pir_z_in_shell])
            rotate([-90, 0, 0])
            cylinder(d = PIR_MOUNT_D + 4, h = SH_WALL + 1,
                     center = true);

        // --- USB-C access (right face +X) ---
        translate([SH_W / 2 - SH_WALL / 2, 0, usb_z_in_shell])
            cube([SH_WALL + 1, XIAO_USB.x + 4, XIAO_USB.z + 4],
                 center = true);

        // --- Bottom cable exit (center) ---
        translate([0, 0, -0.1])
            cylinder(d = 9, h = SH_WALL + 1);
    }

    // --- Internal alignment tabs (friction fit to chassis) ---
    tab_h = 8;
    for (sx = [-1, 1])
        translate([sx * (CW / 2 + tol + 0.4), 0, SH_GAP + TOTAL_H / 2 - tab_h / 2])
            cube([1.2, 10, tab_h], center = true);
}


// ======================== PIR INSERTS ============================

// AM312 mini PIR adapter
module pir_am312() {
    h = wall + 2;
    difference() {
        union() {
            // Body (fits into PIR mount hole)
            cylinder(d = PIR_MOUNT_D - tol * 2, h = h);
            // Retention flange (sits against inside wall)
            cylinder(d = PIR_MOUNT_D + 2.5, h = 1.5);
        }
        // AM312 bore
        translate([0, 0, -0.1])
            cylinder(d = AM312_D + tol * 2, h = h + 0.2);
    }
}

// HC-SR501 full-size PIR mount
module pir_hcsr501() {
    h = 6;
    difference() {
        union() {
            cylinder(d = PIR_MOUNT_D - tol * 2, h = h);
            cylinder(d = PIR_MOUNT_D + 2.5, h = 1.5);
        }
        // Lens recess
        translate([0, 0, 1.5])
            cylinder(d = SR501_D + tol * 2, h = h);
        // Wiring slot
        translate([0, -PIR_MOUNT_D / 2, h / 2])
            cube([6, 4, h + 1], center = true);
    }
}

// Blank cap (no PIR)
module pir_blank() {
    difference() {
        union() {
            cylinder(d = PIR_MOUNT_D - tol * 2, h = wall + 0.5);
            cylinder(d = PIR_MOUNT_D + 2.5, h = 1.5);
        }
        // Decorative concentric rings
        for (r = [5, 10, 15])
            translate([0, 0, wall + 0.5 - 0.3])
                difference() {
                    cylinder(r = r + 0.5, h = 0.4);
                    cylinder(r = r, h = 0.5);
                }
    }
}


// ======================== ASSEMBLY / RENDER ======================

module assembly() {
    explode = 8;  // gap between parts for visibility

    // Bottom half — sensor chamber
    color("DimGray")
        bottom_half();

    // Top half — MCU chamber (positioned above barrier + air gap)
    color("SlateGray")
        translate([0, 0, BH + BAR_AIR + explode])
        top_half();

    // Outer shell (transparent)
    %color("SteelBlue", 0.12)
        translate([0, 0, -SH_GAP - explode])
        outer_shell();

    // PIR insert (transparent)
    %color("Orange", 0.5)
        translate([0, CD / 2 + 1, wall + SENS_INT.z * 0.55])
        rotate([-90, 0, 0])
        pir_am312();

    // --- Ghost components (for visual check) ---
    // MH-Z19C
    %color("DarkGreen", 0.3)
        translate([-SENS_INT.x / 4 + 2, 0, wall + 3])
        cube(MHZ19, center = true);

    // BME680
    %color("Purple", 0.3)
        translate([SENS_INT.x / 4, 0, wall + BME680.z / 2 + 1])
        cube(BME680, center = true);

    // XIAO ESP32-C6 (in MCU chamber)
    xiao_z = BH + BAR_AIR + explode + XIAO_PIN_H;
    xiao_cx = CW / 2 - wall - XIAO.x / 2 - 1;
    %color("SeaGreen", 0.3)
        translate([xiao_cx, 0, xiao_z + XIAO.z / 2])
        cube(XIAO, center = true);
}

// --- Part selector ---
if (part == "assembly") {
    assembly();
}
else if (part == "bottom") {
    // Print orientation: as-is (flat bottom on bed, cavity up)
    bottom_half();
}
else if (part == "top") {
    // Print orientation: flip so ceiling on bed, cavity + standoffs up
    translate([0, 0, TH])
        rotate([180, 0, 0])
        top_half();
}
else if (part == "top_fan") {
    translate([0, 0, TFH])
        rotate([180, 0, 0])
        top_fan_half();
}
else if (part == "shell") {
    outer_shell();
}
else if (part == "pir_am312") {
    pir_am312();
}
else if (part == "pir_hcsr501") {
    pir_hcsr501();
}
else if (part == "pir_blank") {
    pir_blank();
}
