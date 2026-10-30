"""Detect suspended or interrupted sampling without guessing missing readings."""
def sampling_gap(previous, current, interval):
    if previous is None:
        return False
    wall_delta = current[0]-previous[0]
    monotonic_delta = current[1]-previous[1]
    return (abs(wall_delta-monotonic_delta) > 3 or
            wall_delta > max(30, max(1, interval)*4))
