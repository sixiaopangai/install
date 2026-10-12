# -*- coding: utf-8 -*-
import os
import time
from .base import BaseTool
from .base import PrintUtils,CmdTask,FileUtils,AptUtils,ChooseTask
from .base import osversion
from .base import run_tool_file



ubuntu_ports_sources_template = """
deb <sources>/ <code-name> main restricted universe multiverse
deb <sources>/ <code-name>-updates main restricted universe multiverse
deb <sources>/ <code-name>-backports main restricted universe multiverse
deb <sources>/ <code-name>-security main restricted universe multiverse
"""
ubuntu_amd64_sources_template = """
deb <sources>/ <code-name> main restricted universe multiverse
deb <sources>/ <code-name>-updates main restricted universe multiverse
deb <sources>/ <code-name>-backports main restricted universe multiverse
deb <sources>/ <code-name>-security main restricted universe multiverse
"""
# Debian 10 及更早: 安全源路径是 <code-name>/updates
debian_old_sources_template = """
deb <sources>/ <code-name> main contrib non-free
deb <sources>/ <code-name>-updates main contrib non-free
deb <sources>/ <code-name>-backports main contrib non-free
deb <sources>-security <code-name>/updates main contrib non-free
"""
# Debian 11 起: 安全源改为 <code-name>-security
debian_amd64_sources_template = """
deb <sources>/ <code-name> main contrib non-free
deb <sources>/ <code-name>-updates main contrib non-free
deb <sources>/ <code-name>-backports main contrib non-free
deb <sources>-security/ <code-name>-security main contrib non-free
"""
# Debian 12 起: 固件单独拆到 non-free-firmware
debian_firmware_sources_template = """
deb <sources>/ <code-name> main contrib non-free non-free-firmware
deb <sources>/ <code-name>-updates main contrib non-free non-free-firmware
deb <sources>/ <code-name>-backports main contrib non-free non-free-firmware
deb <sources>-security/ <code-name>-security main contrib non-free non-free-firmware
"""
ubuntu_ports_deb822_template = """
Types: deb
URIs: <sources>/
Suites: <code-name> <code-name>-updates <code-name>-backports
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg

Types: deb
URIs: <sources>/
Suites: <code-name>-security
Components: main universe restricted multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
"""
ubuntu_amd64_deb822_template = """
Types: deb
URIs: <sources>/
Suites: <code-name> <code-name>-updates <code-name>-backports
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg

# 以下安全更新软件源包含了官方源与镜像站配置，如有需要可自行修改注释切换
Types: deb
URIs: <sources>/
Suites: <code-name>-security
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
"""

# Ubuntu 24.04 起默认使用 deb822 格式的 ubuntu.sources, 不再用 sources.list
ubuntu_deb822_file = '/etc/apt/sources.list.d/ubuntu.sources'


class Tool(BaseTool):
    def __init__(self):
        self.type = BaseTool.TYPE_CONFIG
        self.name = "一键更换系统源"
        self.author = '小鱼'
        self.use_deb822 = False


    def add_ros_source(self):
        """快速添加ROS源"""
        dic = {1:"添加ROS/ROS2源",2:"不添加ROS/ROS2源"}
        code,result = ChooseTask(dic, "请问是否添加ROS和ROS2源？").run()
        if code==2: return
        tool = run_tool_file('tools.tool_install_ros',authorun=False)
        if not tool.support_install(): return False
        tool.add_key()
        tool.add_source()

    def backup_path(self, path):
        """把要清理的源文件/目录改名备份, 而不是直接删除, 出问题可以手动恢复"""
        if not os.path.exists(path):
            return None
        backup = '{}.fishros-bak-{}'.format(path, time.strftime('%Y%m%d%H%M%S'))
        CmdTask('sudo mv {} {}'.format(path, backup)).run()
        return backup

    def backup_third_party_sources(self):
        """
        把 sources.list.d 里的第三方源(除系统自己的 ubuntu.sources 外)挪到备份目录.
        返回备份目录, 没有第三方源时返回 None
        """
        src_dir = '/etc/apt/sources.list.d'
        if not os.path.isdir(src_dir):
            return None
        files = [f for f in os.listdir(src_dir) if f != 'ubuntu.sources']
        if not files:
            return None
        backup = '{}.fishros-bak-{}'.format(src_dir, time.strftime('%Y%m%d%H%M%S'))
        CmdTask('sudo mkdir -p {}'.format(backup)).run()
        for f in files:
            CmdTask('sudo mv {}/{} {}/'.format(src_dir, f, backup)).run()
        return backup

    def clean_old_source(self, auto=False):
        if auto:
            # 全自动模式: 只换系统源, 第三方源先保留, apt update 失败时再挪走(见 change_sys_source)
            code = 1
        else:
            dic = {1:"仅更换系统源",2:"更换系统源并清理第三方源"}
            code,result = ChooseTask(dic, "请选择换源方式,如果不知道选什么请选2").run()
        # 清理前先记下系统是否使用 deb822 格式(24.04+), 否则清理三方源时会连 ubuntu.sources 一起挪走, 就判断不出来了
        self.use_deb822 = os.path.exists(ubuntu_deb822_file)
        backup = '/etc/apt/ubuntu.sources.fishros.bak'
        if self.use_deb822 and not os.path.exists(backup):
            CmdTask('sudo cp {} {}'.format(ubuntu_deb822_file, backup)).run()
        self.backup_path('/etc/apt/sources.list')
        if code==2:
            backup_dir = self.backup_third_party_sources()
            if backup_dir:
                PrintUtils.print_info('第三方源已备份到 {}, 如需恢复可把里面的文件挪回 /etc/apt/sources.list.d/'.format(backup_dir))
            # fix add source failed before config system source
            CmdTask('sudo mkdir -p /etc/apt/sources.list.d').run()

        if auto:
            self.source_method_code = 1
            return

        # 添加选择源的方式
        PrintUtils.print_info("源选择方式说明:")
        PrintUtils.print_info("1. 自动测速选择最快的源: 系统将自动测试各个源的速度，并选择最快的源")
        PrintUtils.print_info("2. 根据测速结果手动选择源: 系统将测试各个源的速度，然后让您从测试结果中选择")

        dic_source_method = {1:"自动测速选择最快的源", 2:"根据测速结果手动选择源"}
        self.source_method_code, _ = ChooseTask(dic_source_method, "请选择源的选择方式").run()

    def get_debian_template(self, codename):
        if codename in ('wheezy', 'jessie', 'stretch', 'buster'):
            return debian_old_sources_template
        if codename == 'bullseye':
            return debian_amd64_sources_template
        return debian_firmware_sources_template

    def get_source_by_system(self,system,codename,arch,failed_sources=[], return_all=False):
        # 实际测试发现，阿里云虽然延时很低，但是带宽也低的离谱，一点都不用心，删掉了
        ubuntu_amd64_sources = [
            "https://mirrors.tuna.tsinghua.edu.cn/ubuntu",
            "https://mirror.sysu.edu.cn/ubuntu",
            # "https://mirrors.aliyun.com/ubuntu",
            # "https://mirrors.163.com/ubuntu",
            "https://mirrors.ustc.edu.cn/ubuntu",
            "https://archive.ubuntu.com/ubuntu",
            "https://mirrors.kernel.org/ubuntu",
            "http://mirrors.tuna.tsinghua.edu.cn/ubuntu",
            "http://mirror.sysu.edu.cn/ubuntu",
            # "http://mirrors.aliyun.com/ubuntu",
            # "http://mirrors.163.com/ubuntu",
            "http://mirrors.ustc.edu.cn/ubuntu",
            "http://archive.ubuntu.com/ubuntu",
            "http://mirrors.kernel.org/ubuntu",
        ]
        ubuntu_ports_sources = [
            "https://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports",
            "https://mirror.sysu.edu.cn/ubuntu-ports",
            "https://mirrors.ustc.edu.cn/ubuntu-ports",
            "https://ports.ubuntu.com/ubuntu-ports",
            "http://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports",
            "http://mirror.sysu.edu.cn/ubuntu-ports",
            "http://mirrors.ustc.edu.cn/ubuntu-ports",
            "http://ports.ubuntu.com/ubuntu-ports",
        ]
        # Debian 的镜像不区分架构, arm64/armhf 和 amd64 用同一套地址
        debian_sources = [
            "https://mirrors.tuna.tsinghua.edu.cn/debian",
            "https://mirror.sysu.edu.cn/debian",
            "https://mirrors.aliyun.com/debian",
            # "https://mirrors.163.com/debian",
            "https://mirrors.ustc.edu.cn/debian",
            "https://deb.debian.org/debian",
            "http://mirrors.tuna.tsinghua.edu.cn/debian",
            "http://mirror.sysu.edu.cn/debian",
            "http://mirrors.aliyun.com/debian",
            # "http://mirrors.163.com/debian",
            "http://mirrors.ustc.edu.cn/debian",
            "http://deb.debian.org/debian",
        ]
        sources = []
        template = ubuntu_amd64_sources_template
        if system=='ubuntu':
            if arch=='amd64':
                sources = ubuntu_amd64_sources
                template = ubuntu_amd64_deb822_template if self.use_deb822 else ubuntu_amd64_sources_template
            else:
                sources = ubuntu_ports_sources
                template = ubuntu_ports_deb822_template if self.use_deb822 else ubuntu_ports_sources_template
        elif system=='debian':
            template = self.get_debian_template(codename)
            sources = debian_sources

        sources = [source for source in sources if source not in failed_sources]
        if len(sources) == 0:
            return None, None
        PrintUtils.print_delay('搜索到可用源:{}'.format(sources),0.002)
        PrintUtils.print_delay('接下来将进行自动测速以为您选择最快的源:')
        fast_source = AptUtils.get_fast_url(sources)
        if len(fast_source) == 0:
            return None, None

        # 手动选择时返回按测速排序后的全部源
        if return_all:
            return fast_source, template
        return fast_source[0], template

    def replace_source(self,failed_sources=[]):
        arch = AptUtils.getArch()
        name = osversion.get_name()
        codename = osversion.get_codename()
        if name.find("ubuntu")>=0:
            system = 'ubuntu'
        elif name.find("debian")>=0:
            system = 'debian'
        else:
            PrintUtils.print_error('当前系统{}暂不支持一键换源'.format(name))
            return None
        if not codename:
            PrintUtils.print_error('获取系统代号失败, 无法自动换源, 请检查 /etc/os-release')
            return None

        PrintUtils.print_delay('检测到当前系统:{} 架构:{} 代号:{},正在为你搜索适合的源...'.format(system,arch,codename))

        # 根据用户选择的方式获取源
        if getattr(self, 'source_method_code', 1) == 2:
            # 根据测速结果手动选择源
            sorted_sources, template = self.get_source_by_system(system, codename, arch, failed_sources, return_all=True)
            if not sorted_sources:
                return None
            source_dict = {}
            for i, src in enumerate(sorted_sources, 1):
                source_dict[i] = src
            PrintUtils.print_info("请从测速结果中选择您想使用的镜像源:")
            code, source = ChooseTask(source_dict, "请选择一个镜像源").run()
            if not source:
                return None
            PrintUtils.print_success('您选择的镜像源:{}'.format(source))
        else:
            # 自动测速选择源
            source, template = self.get_source_by_system(system, codename, arch, failed_sources)
            if not source: return None
            PrintUtils.print_success('为您选择最快镜像源:{}'.format(source))

        data = template.replace("<code-name>",codename).replace('<sources>',source.rstrip('/'))
        if self.use_deb822:
            FileUtils.new('/etc/apt/sources.list.d/','ubuntu.sources',data)
        else:
            FileUtils.new('/etc/apt/','sources.list',data)
        return source


    def change_sys_source(self, auto=False):
        self.clean_old_source(auto=auto)

        failed_sources = []
        result = (-1, [], [])
        source = self.replace_source(failed_sources)
        if source:
            PrintUtils.print_delay("替换镜像源完成，尝试进行更新....")
            result = CmdTask('sudo apt update',100).run()
            # 全自动模式下保留了第三方源, 更新失败多半是它们的问题(密钥过期/源失效), 先挪走再试
            if result[0] != 0 and auto:
                backup_dir = self.backup_third_party_sources()
                if backup_dir:
                    PrintUtils.print_warn('更新失败, 已把可能有问题的第三方源备份到 {} 后重试'.format(backup_dir))
                    result = CmdTask('sudo apt update',100).run()
            if result[0] != 0:
                if getattr(self, 'source_method_code', 1) == 2:
                    PrintUtils.print_warn("您选择的源更新失败，请重新选择其他源")
                while result[0] != 0:
                    failed_sources.append(source)
                    PrintUtils.print_warn("更新失败，尝试更换其他源")
                    source = self.replace_source(failed_sources)
                    if not source:
                        PrintUtils.print_error("没有找到合适的镜像源,臣妾告退!")
                        return
                    result = CmdTask('sudo apt update',100).run()
        else:
            PrintUtils.print_error("没有找到合适的镜像源,臣妾告退!")

        if result[0]==0:
            PrintUtils.print_success("搞定了,不信你看,累死宝宝了，还不快去给小鱼点个赞~")
            PrintUtils.print_info(result[1])
        PrintUtils.print_success("镜像更新完成.....")

    def run(self):
        # 正式的运行
        self.change_sys_source()
        # 添加 ROS Source
        self.add_ros_source()
