import pandas as pd
import numpy as np
from collections import defaultdict
import pickle
import glob
from matplotlib import pyplot as plt


train_data_file_prefix = "../dataSets/training/"
gen_data_file_prefix = "../dataSets/gen_data/"
def link_time_ave_analysis(traj_df, using_file=True, name=""):
    # 按link_id 进行统计， traj_df是广义的，只要是一个df就行。一般是analysis_by_time的子函数。
    analysis_log = ""
    link_time_dict_path = gen_data_file_prefix + name + "_"+"link_time_dict.pkl"
    if glob.glob(link_time_dict_path) and using_file:
        with open(link_time_dict_path, "rb") as f:
            link_dict = pickle.load(f)
    else:
        link_dict = defaultdict(list)
        for row in traj_df["travel_seq"]:
            for link in row.split(";"):
                tmp = link.split("#")
                link_dict[tmp[0]].append(tmp[2])
    if using_file:
        with open(link_time_dict_path, "wb") as f:
                pickle.dump(link_dict, f)
    for link_id in links["link_id"]:
        tmp = np.array(link_dict[str(link_id)]).astype(float)
        #一致性（一刀切）剔除上界和下界分别1%的异常数据
        tmp = tmp[np.where(tmp < np.percentile(tmp, 99))]
        tmp = tmp[np.where(tmp > np.percentile(tmp, 1))]

        single_result = "link_id:{}, mean:{}, max:{}, min:{}, std:{}, coefficient of variation: {}".format(link_id, tmp.mean(), tmp.max(), tmp.min(), tmp.std(), tmp.std()/tmp.mean())
        print(single_result)
        analysis_log += single_result + "\n"
    return analysis_log

def train_local_data_gen(train, link_id, target_routes=None):
    # 用于抽取数据，两个过滤标准，一是路线，而是linkid，暂时现在是路线可以多条，linkid只能有一个。如果要按全部路线进行分析，可以使用analysis_by_time函数
    # extract linkid 123, route a2, a3
    if target_routes != None:
        intersection_id, tollgate_id = target_routes[:, 0], target_routes[:, 1]
        extra_condition = np.array([0])
        for intersection, tollgate in zip(intersection_id, tollgate_id):
            print(intersection, tollgate)
            if extra_condition.any():
                extra_condition = ((train.intersection_id == intersection) & (train.tollgate_id == tollgate)) | extra_condition
            else:
                extra_condition = ((train.intersection_id == intersection) & (train.tollgate_id == tollgate))
        train = train[extra_condition]
    local_data = []
    for i in train.travel_seq:
        for j in i.split(";"):
            if j[0:3] == link_id:
                tmp = j.split("#")
                local_data.append(tmp)
                break
    return local_data

def analysis_by_time(traj_df, group_basis, using_file = False):
    # 可根据分组对数据分类分析,分组的group_basis必须是traj_df中的列名
    group_date = traj_df.groupby(by=group_basis)
    result_log = ""
    for name, group in group_date:
        print(name)
        result_log += str(name) + "\n"
        single_log = link_time_ave_analysis(group,using_file=using_file, name=group_basis + "_" +str(name))
        result_log += single_log
    with open(gen_data_file_prefix + group_basis +"_analysis_log.txt", "w") as f:
        f.write(result_log)

def fill_if_link_id_missing(train, routes, links):
    # 填补路线中，观测点缺失数据
    # 缺失数据不会是该路线中的最后一个linkid和第一个linkid
    # 有两个记录，分别是57942， 105291缺了两段（不止两个link）的数据
    # 这个填充方式有两个缺陷，一是占比问题，二是精度问题，只能精确到秒
    # TODO 验证一下产生的填充值是否正常
    def ratio_compute(miss_sub_route, links):
        # 占比计算
        # miss_sub_root 是一个linkid串，注意跟下面的subroute不一样，下面的linkid的位置串
        tmp = []
        for linkid in miss_sub_route:
            tmp.append(links[links.link_id == linkid]["length"].values[0]/links[links.link_id == linkid]["lanes"].values[0])
        s = sum(tmp)
        tmp = [x/s for x in tmp]
        return tmp
    count = 0
    for i in range(train.shape[0]):
        j = train.iloc[i,:]
        route = routes[(routes.intersection_id == j.intersection_id) & (routes.tollgate_id == j.tollgate_id)]
        route_link_seq = route["link_seq"].values[0].split(",")
        tmp = j.travel_seq.split(";")
        diff = set(route_link_seq).difference(set([x[0:3] for x in tmp]))
        # diff = list(diff)
        if len(diff) > 0:
            count += 1
            pos = [route_link_seq.index(x) for x in diff]
            pos = sorted(pos)
            # print(diff)
            # print(pos)
            if (pos[-1] - pos[0]) != (len(pos)-1):
                # 判断是否多个连续缺失
                for i in range(len(pos)-1, 0, -1):
                    #寻找大于两段缺失段的缺失点
                    if (pos[0:i][-1] -pos[0:i][0]) != (len(pos[0:i])-1):
                        continue
                    else:
                        #找到切割点
                        sub_route1 = pos[0:i]
                        sub_route2 = pos[i:]
                        missing_sub_route = [sub_route1, sub_route2]
                        break
            else:
                missing_sub_route = [pos]
            for sub_route in missing_sub_route:
                # print(sub_route)
                # print(route_link_seq[sub_route[0]-1])
                # print("right", route_link_seq[sub_route[-1]+1])
                # print(j)
                # print(j.travel_seq)
                left = [x for x in tmp if route_link_seq[sub_route[0]-1] == x[0:3]]
                right = [x for x in tmp if route_link_seq[sub_route[-1]+1] == x[0:3]]
                # print(left)
                # print(right)
                miss_sum_time_length = (pd.to_datetime(right[0].split("#")[1]) - pd.to_datetime(left[0].split("#")[1])).seconds - float(left[0].split("#")[2])
                sub_route_link_id = []
                for x in sub_route:
                    sub_route_link_id.append(route_link_seq[x])
                ratio_list = ratio_compute(sub_route_link_id, links)
                insert_seq = []
                cum_ratio = 0
                for link, ratio in zip(sub_route_link_id, ratio_list):
                    insert_string = ""
                    insert_string += link
                    insert_string += "#"
                    insert_string += str(pd.to_datetime(tmp[sub_route[0] - 1].split("#")[1]) + pd.to_timedelta(tmp[sub_route[0] - 1].split("#")[2]+"S") + pd.to_timedelta(str(miss_sum_time_length*cum_ratio)+"S"))
                    insert_string += "#" + str(miss_sum_time_length*ratio)
                    insert_seq.append(insert_string)
                    cum_ratio += ratio
                tmp = tmp[0:sub_route[0]] + insert_seq + tmp[sub_route[0]:]
            new_seq = ";".join(tmp)
            train.iloc[i,4] = new_seq
            print("new_seq", new_seq)
            print("old seq", j.travel_seq)
        else:
            continue
            # p = [s+1 for s in pos]
            # if p[0:-1] != pos[1:]:
            #     print(route, j.intersection_id, j.tollgate_id)
            #     print(i, route_link_seq, tmp, diff)
            #     print(pos[1:], p[0:-1])
    print(count)
    return train

def time_seq_analysis(local_array, link_id=None, granularity="hour", sub_image=True):
    local_data = pd.DataFrame(local_array)
    local_data.columns = ["link_id", "time", "length"]
    local_data["length"] = local_data.length.astype(float)
    # 一致性（一刀切）剔除上界和下界分别1%的异常数据
    local_data = local_data[local_data.length < np.percentile(local_data.length.values, 99)]
    local_data = local_data[local_data.length > np.percentile(local_data.length.values, 1)]
    local_data["time"] = pd.to_datetime(local_data["time"])
    local_data["starting_weekday"] = local_data["time"].dt.weekday
    local_data["starting_date"] = local_data["time"].map(pd.datetime.date)
    local_data["starting_hour"] = local_data["time"].dt.hour
    local_data["minute"] = local_data["time"].dt.hour*60 + local_data["time"].dt.minute
    group_by_weekday = local_data.groupby(by=["starting_weekday"])
    extracted_data = defaultdict(list)
    plt.figure()
    # TODO 加散点图，每张图上面的数据量，以及统计信息
    plt.title("link_id:{} X--{}, Y--average_time_length, categorized_by_weekday".format(link_id, granularity))
    for name1, group_weekday in group_by_weekday:
        print(name1)
        if granularity == "hour":
            group_by_hour = group_weekday.groupby(by="starting_hour").mean()
            label = "id:{},day:{}".format(link_id, name1)
            #print(group_by_hour)
            plt.plot(group_by_hour.length, label=label)
            extracted_data[name1] = list(group_by_hour.length.values)
        elif ("minute" in granularity) and sub_image:
            fine_granularity = int(granularity.split("_")[1])
            group_weekday["minute"] = (group_weekday["minute"]/fine_granularity).astype(int)
            # print(group_weekday["minute"])
            label = "id:{},day:{}".format(link_id, name1)
            plt.tight_layout()
            plt.subplot(int("42{}".format(name1+1)))
            # 散点图
            # plt.scatter(group_weekday["minute"], group_weekday["length"], label=label)
            # 均值曲线图
            group_by_minute = group_weekday.groupby(by="minute").mean()
            extracted_data[name1] = list(group_by_minute.length.values)
            plt.plot(group_by_minute.length, label=label)
            ax = plt.subplot(int("42{}".format(name1+1)))
            ax.set_title("link_id:{}, weekday:{}".format(link_id, name1))
        elif ("minute" in granularity) and (not sub_image):
            fine_granularity = int(granularity.split("_")[1])
            group_weekday["minute"] = (group_weekday["minute"]/fine_granularity).astype(int)
            label = "id:{},day:{}".format(link_id, name1)
            # 散点图
            # plt.scatter(group_weekday["minute"], group_weekday["length"], label=label)
            # 均值曲线图
            group_by_minute = group_weekday.groupby(by="minute").mean()
            extracted_data[name1] = list(group_by_minute.length.values)
            plt.plot(group_by_minute.length, label=label)
            plt.title("link_id:{} X--{},Y--time_length,categorized_by_weekday_{}".format(link_id, granularity, name1))
            # plt.savefig(gen_data_file_prefix+"image/link_id_{}_X_{}_Y_scatter_time_length_weekday_{}.png".format(link_id, granularity, name1))
            plt.savefig(gen_data_file_prefix+"image/link_id_{}_X_{}_Y_average_time_length_weekday_{}.png".format(link_id, granularity, name1))
            plt.close()

    # plt.title("link_id:{} X--{}, Y--average_time_length, categorized_by_weekday".format(link_id, granularity))
    if (("minute" in granularity) and sub_image) or (granularity == "hour"):
        # plt.savefig(gen_data_file_prefix+"image/link_id_{}_X_{}_Y_scatter_time_length_weekday.png".format(link_id, granularity, name1))
        plt.savefig(gen_data_file_prefix+"image/link_id_{}_X_{}_Y_average_time_length_weekday.png".format(link_id, granularity, name1))
        # plt.show()
        plt.close()
    return extracted_data

def multi_local_data_gen(traj_df, single_link_id, secondary_cate, target_routes=None, save_file=False):
    # 按linkid，weekday，窗口大小，没有shift产生均值数据
    if glob.glob(gen_data_file_prefix + "link_{}.pkl".format(single_link_id)):
        local_data = np.load(gen_data_file_prefix + "link_{}.pkl".format(single_link_id))
    else:
        local_data = train_local_data_gen(traj_df, single_link_id, target_routes=target_routes)
        local_data = np.array(local_data)
        local_data.dump(gen_data_file_prefix + "link_{}.pkl".format(single_link_id))
    extracted_data = time_seq_analysis(local_data, single_link_id, secondary_cate, sub_image=True)
    if save_file == True:
        with open(gen_data_file_prefix + "mean_data_by_weekday_{}_{}.pkl".format(secondary_cate, single_link_id), "wb") as f:
            pickle.dump(extracted_data, f)


if __name__ == "__main__":
    routes = pd.read_csv(train_data_file_prefix + "routes(table4).csv")
    links = pd.read_csv(train_data_file_prefix + "links(table3).csv")
    links["link_id"] = links.link_id.astype(str)
    if glob.glob(train_data_file_prefix + "trajectories(new)_training.csv"):
        traj_df = pd.read_csv(train_data_file_prefix + "trajectories(new)_training.csv")
    else:
        traj_df = pd.read_csv(train_data_file_prefix + "trajectories(table5)_training.csv")
        traj_df = fill_if_link_id_missing(traj_df, routes, links)
        traj_df.to_csv(train_data_file_prefix + "trajectories(new)_training.csv")
    traj_df["tollgate_id"] = traj_df.tollgate_id.astype(str)
    # print(traj_df.columns)
    # traj_df["starting_time"] = pd.to_datetime(traj_df["starting_time"])
    # traj_df["starting_date"] = traj_df["starting_time"].map(pd.datetime.date)
    # traj_df["starting_hour"] = traj_df["starting_time"].dt.hour
    # traj_df["starting_weekday"] = traj_df["starting_time"].dt.weekday

    # group_basis = "starting_date"
    # group_basis = "starting_hour"
    # group_basis = "starting_weekday"
    # analysis_by_time(traj_df=traj_df, group_basis=group_basis)

    single_link_id = "111"
    target_routes = np.array([["C", 1], ["C", 3], ["B", 1], ["B", 3]])
    secondary_cate = "hour"
    for single_link_id in links.link_id:
        multi_local_data_gen(traj_df, single_link_id, secondary_cate, save_file=False)

