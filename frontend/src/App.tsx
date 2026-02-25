import { useState } from 'react';
import { Layout, Menu, Typography, ConfigProvider } from 'antd';
import { UnorderedListOutlined, PhoneOutlined, UserOutlined, ApiOutlined, FileTextOutlined, DashboardOutlined } from '@ant-design/icons';
import { AllRecordsList } from './components/AllRecordsList';
import { ChatViewer } from './components/ChatViewer';
import { CustomerManagement } from './components/CustomerManagement';
import { FlowManagement } from './components/FlowManagement';
import { PromptManagement } from './components/PromptManagement';
import { MonitoringDashboard } from './components/MonitoringDashboard';

const { Header, Content, Sider } = Layout;
const { Title } = Typography;

function App() {
  const [selectedMenu, setSelectedMenu] = useState('monitoring');
  const [selectedContactId, setSelectedContactId] = useState<string | null>(null);

  const handleSelectRecord = (contactId: string) => {
    setSelectedContactId(contactId);
  };

  const handleCloseViewer = () => {
    setSelectedContactId(null);
  };

  const menuItems = [
    {
      key: 'monitoring',
      icon: <DashboardOutlined />,
      label: 'Monitoring',
    },
    {
      key: 'customers',
      icon: <UserOutlined />,
      label: 'Customer Management',
    },
    {
      key: 'prompts',
      icon: <FileTextOutlined />,
      label: 'Prompt Templates',
    },
    {
      key: 'flows',
      icon: <ApiOutlined />,
      label: 'Flow Configuration',
    },
    {
      key: 'records',
      icon: <UnorderedListOutlined />,
      label: 'Call Records',
    },
  ];

  return (
    <ConfigProvider>
      <Layout style={{ minHeight: '100vh' }}>
        <Header
          style={{
            display: 'flex',
            alignItems: 'center',
            backgroundColor: '#1677ff',
            padding: '0 24px',
          }}
        >
          <PhoneOutlined style={{ fontSize: 24, color: '#fff', marginRight: 12 }} />
          <Title level={3} style={{ color: '#fff', margin: 0 }}>
            Voice Agent Platform
          </Title>
        </Header>
        <Layout>
          <Sider width={200} style={{ background: '#fff' }}>
            <Menu
              mode="inline"
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
                background: '#f0f2f5',
                borderRadius: 8,
              }}
            >
              {selectedMenu === 'monitoring' && <MonitoringDashboard />}
              {selectedMenu === 'customers' && <CustomerManagement />}
              {selectedMenu === 'prompts' && <PromptManagement />}
              {selectedMenu === 'flows' && <FlowManagement />}
              {selectedMenu === 'records' && (
                <div style={{ display: 'flex', gap: 24 }}>
                  <div style={{ flex: 1 }}>
                    <AllRecordsList onSelectRecord={handleSelectRecord} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <ChatViewer
                      contactId={selectedContactId}
                      onClose={handleCloseViewer}
                    />
                  </div>
                </div>
              )}
            </Content>
          </Layout>
        </Layout>
      </Layout>
    </ConfigProvider>
  );
}

export default App;
