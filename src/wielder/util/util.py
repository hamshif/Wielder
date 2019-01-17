

def replace_last(full, sub, rep=''):

    end = ''
    count = 0
    for c in reversed(full):
        count = count + 1
        end = c + end
        # print(end)

        if sub in end:
            return full[:-count] + end.replace(sub, rep)

    return full
