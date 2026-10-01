//! Host interpretation of the averaged wheel normal at a rounded coping shoulder.

/// The stock vert band (a near-vertical normal, a steep upward departure, no transfer) reads as a vertical wall.
/// `assist` (Atelier, 0 is stock) widens it to quarters that end short of vertical, down to about 50 degrees at 1,
/// and removes the speed such a lip throws towards the deck, so the air comes back down into the transition.
pub(crate) fn vert_departure(n: [f32;4], v: [f32;4], direction: f32, assist: f32) -> ([f32;4], [f32;4]) {
    let speed = (v[0]*v[0]+v[1]*v[1]+v[2]*v[2]).sqrt();
    let horizontal = (n[0]*n[0]+n[2]*n[2]).sqrt();
    if direction >= 0.5 || horizontal < 1e-6 { return (n, v); }
    let wall = [n[0]/horizontal, 0., n[2]/horizontal, 0.];
    if n[1].abs() < 0.25 && v[1] > 0.8*speed && horizontal > 0.9 { return (wall, v); }
    let reach = 0.25 + 0.4*assist.clamp(0., 1.);
    // The climb across the lip, without the speed along the coping; a quarter's tangent climbs at sqrt(1 - n.y^2).
    let into = v[0]*wall[0] + v[2]*wall[2];
    let climb = v[1] / (v[1]*v[1] + into*into).sqrt().max(1e-6);
    if assist <= 0. || n[1] <= 0. || n[1] >= reach || v[1] <= 0. || climb < (1. - reach*reach).sqrt() - 0.1 {
        return (n, v);
    }
    let out = into.min(0.);
    (wall, [v[0] - wall[0]*out, v[1], v[2] - wall[2]*out, v[3]])
}

#[cfg(test)]
mod departure_tests {
    use super::vert_departure;
    #[test]
    fn upward_coping_departure_does_not_turn_vertical_speed_into_a_transfer() {
        let n=[0.,0.1857,-0.9826,0.];
        let v=[0.38,4.75,0.14,0.];
        assert_eq!(vert_departure(n,v,0.,0.),([0.,0.,-1.,0.],v));
        assert_eq!(vert_departure(n,v,0.8,0.),(n,v));
    }
    #[test]
    fn banks_flat_pops_and_descending_contacts_keep_their_native_normal() {
        for n in [[0.,1.,0.,0.],[0.,0.707,-0.707,0.],[0.,0.3,-0.954,0.]] {
            assert_eq!(vert_departure(n,[0.,6.,1.,0.],0.,0.),(n,[0.,6.,1.,0.]));
        }
        let n=[0.,0.1857,-0.9826,0.];
        assert_eq!(vert_departure(n,[0.,-4.,0.,0.],0.,0.),(n,[0.,-4.,0.,0.]));
        assert_eq!(vert_departure(n,[5.,1.,0.,0.],0.,0.),(n,[5.,1.,0.,0.]));
    }
    #[test]
    fn the_assist_reaches_a_shallower_lip_and_keeps_the_air_over_the_transition() {
        // A 60 degree lip facing -z, climbed straight: the tangent leans 0.5 of the speed towards the deck (+z).
        let n=[0.,0.5,-0.866,0.];
        let v=[0.,0.866*10.,0.5*10.,0.];
        assert_eq!(vert_departure(n,v,0.,0.),(n,v));
        let (wall, kept) = vert_departure(n,v,0.,1.);
        assert_eq!(wall,[0.,0.,-1.,0.]);
        assert_eq!(kept,[0.,v[1],0.,0.]);
        // Half strength reaches 70 degree lips, not this one; a transfer keeps the lip, a carve its speed along the coping.
        assert_eq!(vert_departure(n,v,0.,0.5),(n,v));
        assert_eq!(vert_departure([0.,0.34,-0.94,0.],[0.,9.4,3.4,0.],0.,0.5).0,[0.,0.,-1.,0.]);
        assert_eq!(vert_departure(n,v,1.,1.),(n,v));
        let carve=[6.,8.66,5.,0.];
        assert_eq!(vert_departure(n,carve,0.,1.).1,[6.,8.66,0.,0.]);
        // A kicker (45 degrees) and anything below it launch as they always did.
        let kicker=[0.,0.707,-0.707,0.];
        assert_eq!(vert_departure(kicker,[0.,7.07,7.07,0.],0.,1.),(kicker,[0.,7.07,7.07,0.]));
    }
}
