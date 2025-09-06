import { mutation } from "./_generated/server";
import { v } from "convex/values";

export const insertFakeJobs = mutation({
  args: {},
  handler: async (ctx) => {
    const fakeJobs = [
      {
        title: "Senior Software Engineer",
        company: "TechCorp Inc.",
        description: "We're looking for a senior software engineer to join our growing team. You'll work on cutting-edge web applications using React, Node.js, and cloud technologies. Strong problem-solving skills and 5+ years of experience required.",
        location: "San Francisco, CA",
        remote: true,
        level: "senior" as const,
        totalCompensation: 180000,
        url: "https://techcorp.com/careers/senior-engineer",
        postedAt: Date.now() - 1000 * 60 * 60 * 2, // 2 hours ago
      },
      {
        title: "Frontend Developer",
        company: "StartupXYZ",
        description: "Join our fast-paced startup as a frontend developer! You'll be responsible for building beautiful, responsive user interfaces using React, TypeScript, and modern CSS frameworks. Perfect for someone who loves creating amazing user experiences.",
        location: "New York, NY",
        remote: false,
        level: "mid" as const,
        totalCompensation: 120000,
        url: "https://startupxyz.com/jobs/frontend-dev",
        postedAt: Date.now() - 1000 * 60 * 60 * 4, // 4 hours ago
      },
      {
        title: "Full Stack Developer",
        company: "Digital Solutions LLC",
        description: "We need a versatile full stack developer who can work across our entire technology stack. Experience with Python, Django, React, and PostgreSQL preferred. Great opportunity to work on diverse projects and grow your skills.",
        location: "Austin, TX",
        remote: true,
        level: "mid" as const,
        totalCompensation: 135000,
        url: "https://digitalsolutions.com/careers/fullstack",
        postedAt: Date.now() - 1000 * 60 * 60 * 6, // 6 hours ago
      },
      {
        title: "Junior Web Developer",
        company: "WebWorks Agency",
        description: "Perfect entry-level position for a recent graduate or career changer! You'll learn modern web development practices while working on client projects. We provide mentorship and training in HTML, CSS, JavaScript, and React.",
        location: "Denver, CO",
        remote: false,
        level: "junior" as const,
        totalCompensation: 75000,
        url: "https://webworks.com/jobs/junior-dev",
        postedAt: Date.now() - 1000 * 60 * 60 * 8, // 8 hours ago
      },
      {
        title: "Staff Software Engineer",
        company: "MegaTech Corporation",
        description: "Lead technical initiatives and mentor other engineers in our platform team. You'll architect scalable systems, drive technical decisions, and work on high-impact projects. 8+ years of experience and strong leadership skills required.",
        location: "Seattle, WA",
        remote: true,
        level: "staff" as const,
        totalCompensation: 250000,
        url: "https://megatech.com/careers/staff-engineer",
        postedAt: Date.now() - 1000 * 60 * 60 * 10, // 10 hours ago
      },
      {
        title: "React Developer",
        company: "InnovateNow",
        description: "Specialized React developer needed for our product team. You'll build complex user interfaces, optimize performance, and collaborate with designers and backend engineers. Strong React, Redux, and TypeScript skills essential.",
        location: "Boston, MA",
        remote: true,
        level: "senior" as const,
        totalCompensation: 165000,
        url: "https://innovatenow.com/jobs/react-dev",
        postedAt: Date.now() - 1000 * 60 * 60 * 12, // 12 hours ago
      },
      {
        title: "Backend Engineer",
        company: "DataFlow Systems",
        description: "Join our backend team to build robust APIs and data processing systems. Experience with Node.js, Python, or Go required. You'll work on high-throughput systems handling millions of requests per day.",
        location: "Chicago, IL",
        remote: false,
        level: "mid" as const,
        totalCompensation: 140000,
        url: "https://dataflow.com/careers/backend-engineer",
        postedAt: Date.now() - 1000 * 60 * 60 * 14, // 14 hours ago
      },
      {
        title: "DevOps Engineer",
        company: "CloudFirst Technologies",
        description: "Help us scale our infrastructure and improve deployment processes. Experience with AWS, Docker, Kubernetes, and CI/CD pipelines required. You'll work on automation, monitoring, and security improvements.",
        location: "Portland, OR",
        remote: true,
        level: "senior" as const,
        totalCompensation: 155000,
        url: "https://cloudfirst.com/jobs/devops",
        postedAt: Date.now() - 1000 * 60 * 60 * 16, // 16 hours ago
      },
      {
        title: "Mobile App Developer",
        company: "AppMakers Studio",
        description: "Develop cross-platform mobile applications using React Native. You'll work on consumer-facing apps with millions of users. Experience with mobile development, app store deployment, and performance optimization preferred.",
        location: "Los Angeles, CA",
        remote: false,
        level: "mid" as const,
        totalCompensation: 130000,
        url: "https://appmakers.com/careers/mobile-dev",
        postedAt: Date.now() - 1000 * 60 * 60 * 18, // 18 hours ago
      },
      {
        title: "Software Engineering Intern",
        company: "Future Tech Labs",
        description: "Summer internship program for computer science students. You'll work on real projects alongside experienced engineers, attend tech talks, and participate in code reviews. Great opportunity to gain industry experience.",
        location: "Palo Alto, CA",
        remote: false,
        level: "junior" as const,
        totalCompensation: 45000,
        url: "https://futuretechlabs.com/internships/swe",
        postedAt: Date.now() - 1000 * 60 * 60 * 20, // 20 hours ago
      },
    ];

    const insertedJobs = [];
    for (const job of fakeJobs) {
      const jobId = await ctx.db.insert("jobs", job);
      insertedJobs.push(jobId);
    }

    return {
      success: true,
      message: `Inserted ${insertedJobs.length} fake jobs`,
      jobIds: insertedJobs,
    };
  },
});
