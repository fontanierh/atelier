//! Host interpretation of the averaged wheel normal at a rounded coping shoulder.

pub(crate) fn vert_departure_normal(n: [f32;4], v: [f32;4], direction: f32) -> [f32;4] {
    let speed = (v[0]*v[0]+v[1]*v[1]+v[2]*v[2]).sqrt();
    let horizontal = (n[0]*n[0]+n[2]*n[2]).sqrt();
    if n[1].abs() < 0.25 && v[1] > 0.8*speed && direction < 0.5 && horizontal > 0.9 {
        [n[0]/horizontal, 0., n[2]/horizontal, 0.]
    } else { n }
}

#[cfg(test)]
mod departure_tests {
    use super::vert_departure_normal;
    #[test]
    fn upward_coping_departure_does_not_turn_vertical_speed_into_a_transfer() {
        let n=[0.,0.1857,-0.9826,0.];
        assert_eq!(vert_departure_normal(n,[0.38,4.75,0.14,0.],0.),[0.,0.,-1.,0.]);
        assert_eq!(vert_departure_normal(n,[0.38,4.75,0.14,0.],0.8),n);
    }
    #[test]
    fn banks_flat_pops_and_descending_contacts_keep_their_native_normal() {
        for n in [[0.,1.,0.,0.],[0.,0.707,-0.707,0.],[0.,0.3,-0.954,0.]] {
            assert_eq!(vert_departure_normal(n,[0.,6.,1.,0.],0.),n);
        }
        let n=[0.,0.1857,-0.9826,0.];
        assert_eq!(vert_departure_normal(n,[0.,-4.,0.,0.],0.),n);
        assert_eq!(vert_departure_normal(n,[5.,1.,0.,0.],0.),n);
    }
}
