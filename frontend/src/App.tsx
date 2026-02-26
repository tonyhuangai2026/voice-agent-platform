import { useState, useEffect } from 'react';
import { Layout, Menu, Typography, ConfigProvider, Space, Select, Spin, Button, Modal } from 'antd';
import {
  UploadOutlined,
  UnorderedListOutlined,
  PhoneOutlined,
  UserOutlined,
  ApiOutlined,
  FileTextOutlined,
  DashboardOutlined,
  ProjectOutlined,
  BarChartOutlined,
  HistoryOutlined,
  SettingOutlined,
  TagsOutlined,
  LogoutOutlined,
} from '@ant-design/icons';
import { ProjectProvider, useProject } from './contexts/ProjectContext';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { listProjects } from './api';
import { UploadPanel } from './components/UploadPanel';
import { AllRecordsList } from './components/AllRecordsList';
import { ChatViewer } from './components/ChatViewer';
import { CustomerManagement } from './components/CustomerManagement';
import { FlowManagement } from './components/FlowManagement';
import { PromptManagement } from './components/PromptManagement';
import { LiveMonitor } from './components/LiveMonitor';
import { ProjectManagement } from './components/ProjectManagement';
import { ProjectDashboard } from './components/ProjectDashboard';
import { CallHistoryViewer } from './components/CallHistoryViewer';
import { LabelManagement } from './components/LabelManagement';
import { Login } from './components/Login';

const { Header, Content, Sider } = Layout;
const { Title, Text } = Typography;

function AppContent() {
  const [selectedMenu, setSelectedMenu] = useState('dashboard');
  const [selectedContactId, setSelectedContactId] = useState<string | null>(null);
  const [projectModalVisible, setProjectModalVisible] = useState(false);

  const { currentProject, setCurrentProject, projects, setProjects, loading, setLoading } = useProject();
  const { user, logout } = useAuth();

  // Load projects on mount
  useEffect(() => {
    const loadProjects = async () => {
      setLoading(true);
      try {
        const data = await listProjects('active');
        setProjects(data.projects);
        // Auto-select first project if none selected
        if (!currentProject && data.projects.length > 0) {
          setCurrentProject(data.projects[0]);
        }
      } catch (error) {
        console.error('Failed to load projects:', error);
      } finally {
        setLoading(false);
      }
    };
    loadProjects();
  }, []);

  const handleSelectRecord = (contactId: string) => {
    setSelectedContactId(contactId);
  };

  const handleCloseViewer = () => {
    setSelectedContactId(null);
  };

  const menuItems = [
    {
      key: 'dashboard',
      icon: <BarChartOutlined />,
      label: 'Dashboard',
    },
    {
      key: 'monitor',
      icon: <DashboardOutlined />,
      label: 'Live Monitor',
    },
    {
      key: 'call-history',
      icon: <HistoryOutlined />,
      label: 'Call History',
    },
    {
      key: 'customers',
      icon: <UserOutlined />,
      label: 'Customers',
    },
    {
      key: 'prompts',
      icon: <FileTextOutlined />,
      label: 'Prompts',
    },
    {
      key: 'flows',
      icon: <ApiOutlined />,
      label: 'Flows',
    },
    {
      key: 'labels',
      icon: <TagsOutlined />,
      label: 'Labels',
    },
    {
      key: 'records',
      icon: <UnorderedListOutlined />,
      label: 'Records',
    },
    {
      key: 'upload',
      icon: <UploadOutlined />,
      label: 'Upload',
    },
  ];

  return (
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: '#667eea',
          colorBgContainer: '#ffffff',
          colorBgElevated: '#ffffff',
          colorBgLayout: '#f5f5f5',
          borderRadius: 8,
        },
        components: {
          Layout: {
            headerBg: '#001529',
            siderBg: '#001529',
            bodyBg: '#f5f5f5',
          },
        },
      }}
    >
      <Layout style={{ minHeight: '100vh' }}>
        <Header
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            backgroundColor: '#001529',
            padding: '0 24px',
          }}
        >
          <Space align="center">
            <PhoneOutlined style={{ fontSize: 24, color: '#667eea', marginRight: 12 }} />
            <Title level={3} style={{ color: '#fff', margin: 0 }}>
              Voice Agent Platform
            </Title>
          </Space>

          <Space align="center" size="middle">
            <ProjectOutlined style={{ fontSize: 16, color: '#fff' }} />
            {loading ? (
              <Spin size="small" />
            ) : (
              <>
                <Select
                  value={currentProject?.project_id}
                  onChange={(value) => {
                    const project = projects.find((p) => p.project_id === value);
                    setCurrentProject(project || null);
                  }}
                  style={{ minWidth: 200 }}
                  placeholder="Select Project"
                  options={projects.map((p) => ({
                    label: p.project_name,
                    value: p.project_id,
                  }))}
                />
                <Button
                  type="link"
                  icon={<SettingOutlined />}
                  onClick={() => setProjectModalVisible(true)}
                  style={{ color: '#fff' }}
                >
                  Manage
                </Button>
              </>
            )}

            <Text style={{ color: 'rgba(255, 255, 255, 0.65)', marginLeft: 24 }}>
              {user?.name || user?.email}
            </Text>
            <Button
              type="link"
              icon={<LogoutOutlined />}
              onClick={logout}
              style={{ color: '#fff' }}
            >
              Logout
            </Button>
          </Space>
        </Header>
        <Layout>
          <Sider
            width={200}
            style={{
              borderRight: '1px solid #f0f0f0',
              background: '#001529',
            }}
          >
            <Menu
              mode="inline"
              theme="dark"
              selectedKeys={[selectedMenu]}
              onClick={({ key }) => {
                setSelectedMenu(key);
                setSelectedContactId(null);
              }}
              style={{ height: '100%', borderRight: 0 }}
              items={menuItems}
            />
          </Sider>
          <Layout style={{ padding: '24px' }}>
            <Content
              style={{
                padding: 24,
                margin: 0,
                minHeight: 280,
                borderRadius: 8,
              }}
            >
              {!currentProject && selectedMenu !== 'dashboard' && selectedMenu !== 'monitor' && selectedMenu !== 'call-history' ? (
                <div style={{ textAlign: 'center', paddingTop: 80 }}>
                  <ProjectOutlined style={{ fontSize: 64, color: '#667eea', marginBottom: 16 }} />
                  <Title level={3}>No Project Selected</Title>
                  <Text type="secondary">Please select or create a project to get started</Text>
                </div>
              ) : (
                <>
                  {selectedMenu === 'dashboard' && <ProjectDashboard />}
                  {selectedMenu === 'monitor' && <LiveMonitor />}
                  {selectedMenu === 'call-history' && <CallHistoryViewer />}
                  {selectedMenu === 'customers' && <CustomerManagement />}
                  {selectedMenu === 'prompts' && <PromptManagement />}
                  {selectedMenu === 'flows' && <FlowManagement />}
                  {selectedMenu === 'labels' && <LabelManagement />}
                  {selectedMenu === 'upload' && <UploadPanel />}
                  {selectedMenu === 'records' && (
                    <div style={{ display: 'flex', gap: 24 }}>
                      <div style={{ flex: 1 }}>
                        <AllRecordsList onSelectRecord={handleSelectRecord} />
                      </div>
                      <div style={{ flex: 1 }}>
                        <ChatViewer contactId={selectedContactId} onClose={handleCloseViewer} />
                      </div>
                    </div>
                  )}
                </>
              )}

              {/* Project Management Modal */}
              <Modal
                title="Manage Projects"
                open={projectModalVisible}
                onCancel={() => setProjectModalVisible(false)}
                footer={null}
                width={1200}
                destroyOnClose
              >
                <ProjectManagement />
              </Modal>
            </Content>
          </Layout>
        </Layout>
      </Layout>
    </ConfigProvider>
  );
}

function App() {
  return (
    <AuthProvider>
      <ProjectProvider>
        <AuthGuard />
      </ProjectProvider>
    </AuthProvider>
  );
}

function AuthGuard() {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Login />;
  }

  return <AppContent />;
}

export default App;
