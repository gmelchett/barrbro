pcb_usb_depth=35.3;
pcb_usb_width=18.3;
pcb_usb_height=4;

box_width=pcb_usb_width+1.7+8;
box_depth=pcb_usb_depth+0.5+30;
box_bottom_tickness=pcb_usb_height+2;
box_height=box_width;
wall=2;

$fn=30;

usb_connector_width=13;
usb_connector_height=6;

module rounded_box(x, y, z, r) {
    minkowski() {
        cube([x - 2*r, y - 2*r, z - 2*r], center=false);
        sphere(r);
    }
}

module box() {
    difference() {
        rounded_box(box_width,box_depth,box_height,1);
        translate([wall/2,wall/2,box_bottom_tickness])
        cube([box_width-2*wall, box_depth-2*wall, box_height]);
    }       
}

module box_with_holes() {
    difference() {
        box();
        translate([4*wall-1,  box_depth-3, 4*wall-1])
        rotate([90,0,0]) 
        for (i=[0:3]) {
            for (j=[0:3]) {
                translate([i*4, j*4, 0])
                cylinder(h=wall*4, r=1, center=true);
            }
        }
    }
}

module box_with_holes_pcb() {
    difference() {
        box_with_holes();
        translate([box_width/2-pcb_usb_width/2-wall/2,2,2])
        cube([pcb_usb_width,pcb_usb_depth,pcb_usb_height+1]);
        translate([box_width/2-usb_connector_width/2-wall/2,-1, pcb_usb_height])
        cube([usb_connector_width,6, usb_connector_height]);  
    }
    translate([0,box_depth-9, box_bottom_tickness])
    cube([box_width-wall/2,1.5,12]);
    translate([0,box_depth-9+1.5+1.7, box_bottom_tickness])
    cube([box_width/4,1.5,12]);

    translate([box_width*3/4-wall,box_depth-9+1.5+1.7, box_bottom_tickness])
    cube([box_width/4,1.5,12]);

    
}
module box_final() {
    difference() {
        box_with_holes_pcb();
        
        // Left side
        translate([wall/8, wall/2, box_height-wall])
        difference() {
            rotate([0,45,0])
            cube([wall, box_depth, wall]);
            translate([0,0,-wall])
            rotate([0,0,0])
            cube([2*wall, box_depth, wall]);
        }
        // Open end for lid to slide.
        translate([wall/2, box_depth-2*wall, box_height-wall])
        cube([box_width-2*wall, wall*2, wall]);

        // right side
        translate([box_width-wall-wall*1.4, wall/2, box_height-wall])
        difference() {
            rotate([0,45,0])
            cube([wall, box_depth, wall]);
            translate([0,0,-wall])
            rotate([0,0,0])
            cube([2*wall, box_depth, wall]);
        }

        // front
        translate([wall/2, 1.41*wall, box_height-wall])
        difference() {
            rotate([0,45,270])
            cube([wall, box_width-2*wall, wall]);
            translate([0,wall/2,-wall])
            rotate([0,0,270])
            cube([2*wall, box_width-2*wall, wall]);
        }

    }
}
box_final();