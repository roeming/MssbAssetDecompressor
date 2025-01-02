class MultipleRanges:
    def __init__(self) -> None:
        self.__ranges:list[range] = []

    def __overlap(r1:range, r2:range):
        return (
            # if one of the start/stops exists in the other
            (r2.start in r1 or r2.stop in r1) or
            (r1.start in r2 or r1.stop in r2))
    
    def __overlap_or_touch(r1:range, r2:range):
        return (
            # if they overlap on an edge
            r1.start == r2.stop or 
            r2.start == r1.stop or
            MultipleRanges.__overlap(r1, r2))
    
    def __combine_range(r1:range, r2:range)->range:
        if MultipleRanges.__overlap_or_touch(r1, r2):
            all_points = [r1.start, r2.start, r1.stop, r2.stop]
            # if the overlap, just take the max and mins
            return range(min(all_points), max(all_points))
        return None

    def does_overlap(self, r:range):
        return any([MultipleRanges.__overlap(x, r) for x in self.__ranges])

    def add_range(self, r:range):

        overlapping_indices = [i for i, this_range in enumerate(self.__ranges) if MultipleRanges.__overlap_or_touch(r, this_range)]

        if len(overlapping_indices) == 0:
            self.__ranges.append(r)
        else:
            # indices should be next to eachother
            new_range = range(r.start, r.stop)
            for ind in overlapping_indices:
                new_range = MultipleRanges.__combine_range(new_range, self.__ranges[ind])
                assert(new_range != None)

            to_remove_ind = min(overlapping_indices)
            to_remove_count = len(overlapping_indices)
            for _ in range(to_remove_count):
                self.__ranges.pop(to_remove_ind)
            
            self.__ranges.append(new_range)

        self.__ranges.sort(key=lambda x: x.start)

    def __str__(self) -> str:
        return f"{self.__ranges}"
    
    def __repr__(self) -> str:
        return self.__str__()

    def remove_range(self, r:range):
        new_ranges = []

        for old_range in self.__ranges:
            if (old_range.start >= r.start and 
                old_range.stop <= r.stop): # complete overlap, remove
                pass
            elif (old_range.start <= r.start and
                   old_range.stop >= r.start and 
                   old_range.stop <= r.stop): # overlap top
                new_ranges.append(range(old_range.start, r.start))
            elif (old_range.stop >= r.stop and
                   old_range.start >= r.start and 
                   old_range.start <= r.stop): # overlap bottom
                new_ranges.append(range(r.stop, old_range.stop))
            elif (r.start >= old_range.start and 
                  r.stop <= old_range.stop): # overlap middle
                new_ranges.append(range(old_range.start, r.start))
                new_ranges.append(range(r.stop, old_range.stop))            

        self.__ranges = new_ranges

        self.__ranges.sort(key=lambda x: x.start)
    
    def __contains__(self, value):
        if len(self.__ranges) == 0:
            return False 
        # binary search
        max_ind = len(self.__ranges)
        min_ind = 0
        ind = max_ind // 2
        while True:
            this_range = self.__ranges[ind]
            
            if value in this_range:
                return True
            
            if ind == min_ind or ind == len(self.__ranges) - 1:
                return False
            
            if value < this_range.start:
                max_ind = ind
                ind = (ind + min_ind) // 2
            elif value > this_range.stop:
                min_ind = ind
                ind = (ind + max_ind) // 2
            elif value == this_range.stop:
                return False