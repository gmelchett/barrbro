pcb_usb_depth=35.3;
pcb_usb_width=18.3;

pcb_usb_height=4;
box_width=pcb_usb_width+1.7+8-0.5;
box_depth=pcb_usb_depth+0.5+30-3;
box_bottom_tickness=pcb_usb_height+2;
box_height=box_width;
wall=2;

$fn=30;



module box() {
    // Top lid
        translate([wall, wall/2, box_height-wall])
        cube([box_width-3*wall+wall/2, box_depth, wall/2]);

        //translate([wall/2,wall/2,box_bottom_tickness])
        //#cube([box_width-2*wall, box_depth-2*wall, box_height]);
        
        // Left side
        translate([wall/8, wall/2, box_height-wall])
        difference() {
            rotate([0,45,0])
            cube([wall, box_depth, wall]);
            translate([0,-1,-wall])
            rotate([0,0,0])
            cube([2*wall, box_depth+5, wall]);
        }
 
        // right side
        translate([box_width-wall-wall*1.4, wall/2, box_height-wall])
        difference() {
            rotate([0,45,0])
            cube([wall, box_depth, wall]);
            translate([0,-1,-wall])
            rotate([0,0,0])
            cube([2*wall, box_depth+5, wall]);
        }

        // front
        translate([wall/2, 1.41*wall, box_height-wall])
        difference() {
            rotate([0,45,270])
            cube([wall, box_width-2*wall, wall]);
            translate([-wall,wall/2,-wall])
            rotate([0,0,270])
            cube([2*wall, box_width-2*wall+5, wall]);
        }
            
}
difference() {
    box();
    translate([0,-2,box_height-wall/2])
    cube([2*box_depth, 2*box_depth, 2*box_depth]);
}
